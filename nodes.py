import os

import torch
import torch.nn as nn
from safetensors import safe_open
from safetensors.torch import load_file

import folder_paths

try:
    import comfy.model_management as model_management
except Exception:
    model_management = None


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_MODEL_DIR = os.path.join(PLUGIN_DIR, "models")
EXTERNAL_MODEL_DIR = os.path.join(folder_paths.models_dir, "semantic_bridge")

os.makedirs(BUNDLED_MODEL_DIR, exist_ok=True)
os.makedirs(EXTERNAL_MODEL_DIR, exist_ok=True)

# Keep backward compatibility with v0.1/v0.2 and normal ComfyUI model discovery.
try:
    folder_paths.add_model_folder_path("semantic_bridge", EXTERNAL_MODEL_DIR)
except Exception:
    pass

# Cache key: (absolute_path, mtime, compute_device, compute_dtype)
_ADAPTER_CACHE = {}


def _walk_safetensors(root):
    """Return paths relative to root, recursively, using / separators."""
    found = []
    if not os.path.isdir(root):
        return found
    for base, _, files in os.walk(root):
        for filename in files:
            if not filename.lower().endswith(".safetensors"):
                continue
            full = os.path.join(base, filename)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            found.append(rel)
    return sorted(found, key=lambda x: x.lower())


def _external_adapters():
    try:
        files = folder_paths.get_filename_list("semantic_bridge")
    except Exception:
        files = []
    return sorted(
        (x.replace("\\", "/") for x in files if x.lower().endswith(".safetensors")),
        key=lambda x: x.lower(),
    )


def _list_adapters():
    # Bundled models are intentionally listed first. This lets an RH/custom-node
    # package work without any new ComfyUI model category or external directory.
    bundled = _walk_safetensors(BUNDLED_MODEL_DIR)
    external = _external_adapters()

    names = []
    seen = set()
    for name in bundled + external:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            names.append(name)

    # Put the official V1 at the top when present, without changing the stored name.
    preferred = "BUNNY_H3_ActionLogic_Bridge_V1.safetensors"
    for i, name in enumerate(names):
        if name.lower() == preferred.lower():
            names.insert(0, names.pop(i))
            break

    return names if names else ["NO_ADAPTER_FOUND.safetensors"]


def _bundled_path(name):
    # Prevent traversal while still allowing bundled subfolders.
    normalized = os.path.normpath(name.replace("/", os.sep))
    candidate = os.path.abspath(os.path.join(BUNDLED_MODEL_DIR, normalized))
    root = os.path.abspath(BUNDLED_MODEL_DIR)
    if os.path.commonpath([candidate, root]) != root:
        return None
    return candidate if os.path.isfile(candidate) else None


def _external_path(name):
    path = None
    try:
        path = folder_paths.get_full_path("semantic_bridge", name)
    except Exception:
        pass
    if path and os.path.isfile(path):
        return path

    fallback = os.path.join(EXTERNAL_MODEL_DIR, name.replace("/", os.sep))
    return fallback if os.path.isfile(fallback) else None


def _full_adapter_path(name):
    # v0.3 priority: bundled copy first, then old external folder.
    path = _bundled_path(name)
    if path:
        return path, "bundled"

    path = _external_path(name)
    if path:
        return path, "external"

    raise FileNotFoundError(
        "BUNNY H3 Bridge adapter not found.\n\n"
        f"Selected: {name}\n\n"
        "Supported locations:\n"
        f"1) Bundled with node: {BUNDLED_MODEL_DIR}\n"
        f"2) External legacy folder: {EXTERNAL_MODEL_DIR}\n"
    )


def _choose_compute_device():
    # Prefer ComfyUI's active device. Usually cuda:0 on NVIDIA.
    if model_management is not None:
        try:
            device = model_management.get_torch_device()
            if isinstance(device, torch.device):
                if device.type == "cuda" and torch.cuda.is_available():
                    return device
                if device.type != "cpu":
                    return device
        except Exception:
            pass

    if torch.cuda.is_available():
        return torch.device("cuda:0")

    return torch.device("cpu")


def _choose_compute_dtype(device):
    return torch.float16 if device.type == "cuda" else torch.float32


def _rms_normalize_preserve_dtype(x):
    original_dtype = x.dtype
    xf = x.float()
    rms = torch.sqrt(xf.pow(2).mean(dim=-1, keepdim=True) + 1e-6)
    return (xf / rms).to(dtype=original_dtype)


def _match_per_token_preserve_dtype(source, target):
    dtype = source.dtype
    sf = source.float()
    tf = target.float()
    source_rms = torch.sqrt(sf.pow(2).mean(dim=-1, keepdim=True) + 1e-8)
    target_rms = torch.sqrt(tf.pow(2).mean(dim=-1, keepdim=True) + 1e-8)
    return (sf * (target_rms / source_rms)).to(dtype=dtype)


def _match_global_preserve_dtype(source, target):
    dtype = source.dtype
    sf = source.float()
    tf = target.float()
    source_rms = torch.sqrt(sf.pow(2).mean() + 1e-8)
    target_rms = torch.sqrt(tf.pow(2).mean() + 1e-8)
    return (sf * (target_rms / source_rms)).to(dtype=dtype)


class SemanticBridgeMLP(nn.Module):
    def __init__(self, input_dim=5120, hidden_dim=512, output_dim=5120):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim, bias=True)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim, bias=True)
        self.fc3 = nn.Linear(hidden_dim, output_dim, bias=True)
        self.act = nn.SiLU()

    def forward(self, x):
        x = self.act(self.fc1(x))
        x = self.act(self.fc2(x))
        return self.fc3(x)


def _adapter_metadata(path):
    try:
        with safe_open(path, framework="pt", device="cpu") as f:
            return dict(f.metadata() or {})
    except Exception:
        return {}


def _validate_and_infer(weights):
    required = [
        "fc1.weight", "fc1.bias",
        "fc2.weight", "fc2.bias",
        "fc3.weight", "fc3.bias",
    ]
    missing = [k for k in required if k not in weights]
    if missing:
        raise RuntimeError(f"Invalid bridge adapter. Missing tensors: {missing}")

    fc1 = weights["fc1.weight"]
    fc2 = weights["fc2.weight"]
    fc3 = weights["fc3.weight"]

    if fc1.ndim != 2 or fc2.ndim != 2 or fc3.ndim != 2:
        raise RuntimeError("Bridge weights must be 2D Linear-layer tensors.")

    hidden_dim, input_dim = fc1.shape
    hidden2_out, hidden2_in = fc2.shape
    output_dim, hidden3_in = fc3.shape

    if input_dim != 5120 or output_dim != 5120:
        raise RuntimeError(
            "Expected MiniMax H3 bridge dimensions 5120 -> hidden -> hidden -> 5120, "
            f"got {input_dim} -> {hidden_dim} -> {hidden2_out} -> {output_dim}."
        )

    if hidden2_out != hidden_dim or hidden2_in != hidden_dim or hidden3_in != hidden_dim:
        raise RuntimeError(
            "Inconsistent hidden dimensions in bridge adapter: "
            f"fc1={tuple(fc1.shape)}, fc2={tuple(fc2.shape)}, fc3={tuple(fc3.shape)}"
        )

    if tuple(weights["fc1.bias"].shape) != (hidden_dim,):
        raise RuntimeError("Unexpected fc1.bias shape.")
    if tuple(weights["fc2.bias"].shape) != (hidden_dim,):
        raise RuntimeError("Unexpected fc2.bias shape.")
    if tuple(weights["fc3.bias"].shape) != (5120,):
        raise RuntimeError("Unexpected fc3.bias shape.")

    return int(input_dim), int(hidden_dim), int(output_dim)


def _load_adapter(adapter_name, device, dtype):
    path, source = _full_adapter_path(adapter_name)
    mtime = os.path.getmtime(path)
    cache_key = (os.path.abspath(path), float(mtime), str(device), str(dtype))

    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    abs_path = os.path.abspath(path)

    # Remove stale copies of the same file from cache.
    stale = [k for k in _ADAPTER_CACHE if k[0] == abs_path and k != cache_key]
    for k in stale:
        _ADAPTER_CACHE.pop(k, None)

    weights = load_file(path, device="cpu")
    input_dim, hidden_dim, output_dim = _validate_and_infer(weights)

    model = SemanticBridgeMLP(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        output_dim=output_dim,
    )

    with torch.no_grad():
        model.fc1.weight.copy_(weights["fc1.weight"].float())
        model.fc1.bias.copy_(weights["fc1.bias"].float())
        model.fc2.weight.copy_(weights["fc2.weight"].float())
        model.fc2.bias.copy_(weights["fc2.bias"].float())
        model.fc3.weight.copy_(weights["fc3.weight"].float())
        model.fc3.bias.copy_(weights["fc3.bias"].float())

    # Keep the tiny Bridge on the active GPU and use FP16 there.
    model = model.to(device=device, dtype=dtype)
    model.eval()
    model.requires_grad_(False)

    metadata = _adapter_metadata(path)
    payload = {
        "model": model,
        "path": path,
        "source": source,
        "hidden_dim": hidden_dim,
        "metadata": metadata,
        "device": device,
        "dtype": dtype,
    }
    _ADAPTER_CACHE[cache_key] = payload

    version = metadata.get("version") or metadata.get("bridge_version") or "unknown"
    print(
        f"[BUNNY H3 Conditioning Bridge v0.3] Loaded {adapter_name} | "
        f"source={source} | hidden={hidden_dim} | bridge_version={version} | "
        f"compute={device} | dtype={dtype}"
    )
    return payload


def _apply_bridge(conditioning, adapter_name, alpha, magnitude_match, enabled):
    # True bypass: no model load, no tensor copy, no extra compute.
    if not enabled or float(alpha) == 0.0:
        return conditioning

    compute_device = _choose_compute_device()
    compute_dtype = _choose_compute_dtype(compute_device)
    loaded = _load_adapter(adapter_name, compute_device, compute_dtype)
    student = loaded["model"]

    result = []

    for item in conditioning:
        if len(item) != 2:
            raise RuntimeError("Unexpected ComfyUI CONDITIONING structure.")

        native = item[0]
        metadata = item[1]

        if native.ndim != 3 or native.shape[-1] != 5120:
            raise RuntimeError(
                "Expected MiniMax H3 CONDITIONING [B,T,5120], "
                f"got {tuple(native.shape)}. "
                "Place this node after the H3 text-conditioning encoder."
            )

        original_device = native.device
        original_dtype = native.dtype

        # H3 conditioning can live on CPU. Move only this small tensor to the
        # active GPU, run the MLP there, then return it to the original device.
        h = native.to(
            device=compute_device,
            dtype=compute_dtype,
            non_blocking=True,
        )

        x = _rms_normalize_preserve_dtype(h)

        with torch.inference_mode():
            projected = student(x)

        if magnitude_match == "per_token":
            projected = _match_per_token_preserve_dtype(projected, h)
        elif magnitude_match == "global":
            projected = _match_global_preserve_dtype(projected, h)
        elif magnitude_match != "none":
            raise RuntimeError(f"Unknown magnitude_match mode: {magnitude_match}")

        hybrid = h + float(alpha) * (projected - h)

        # Preserve the exact device/dtype contract expected downstream.
        hybrid = hybrid.to(
            device=original_device,
            dtype=original_dtype,
            non_blocking=True,
        )

        new_metadata = dict(metadata)
        new_metadata["bunny_h3_bridge"] = True
        new_metadata["bunny_h3_bridge_alpha"] = float(alpha)
        new_metadata["bunny_h3_bridge_mode"] = magnitude_match
        new_metadata["bunny_h3_bridge_adapter"] = adapter_name
        new_metadata["bunny_h3_bridge_adapter_source"] = loaded["source"]
        new_metadata["bunny_h3_bridge_hidden_dim"] = loaded["hidden_dim"]
        new_metadata["bunny_h3_bridge_compute_device"] = str(compute_device)
        new_metadata["bunny_h3_bridge_compute_dtype"] = str(compute_dtype)

        result.append([hybrid, new_metadata])

    return result


class BunnyH3ConditioningBridge:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "conditioning": ("CONDITIONING",),
                "adapter": (_list_adapters(),),
                "alpha": (
                    "FLOAT",
                    {"default": 0.10, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "magnitude_match": (
                    ["per_token", "global", "none"],
                    {"default": "per_token"},
                ),
                "enabled": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("conditioning",)
    FUNCTION = "apply"
    CATEGORY = "BUNNY/MiniMax H3"

    def apply(self, conditioning, adapter, alpha, magnitude_match, enabled):
        return (
            _apply_bridge(
                conditioning,
                adapter,
                alpha,
                magnitude_match,
                enabled,
            ),
        )


NODE_CLASS_MAPPINGS = {
    "BunnyH3ConditioningBridge": BunnyH3ConditioningBridge,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BunnyH3ConditioningBridge": "BUNNY H3 Conditioning Bridge",
}
