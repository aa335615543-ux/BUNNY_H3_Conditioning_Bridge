# 🐇 BUNNY_H3_Conditioning_Bridge

> **A semantic-conditioning bridge for MiniMax H3.**  
> **一个给 MiniMax H3 使用的语义增强 Bridge。**

It is not a LoRA and it does not rewrite your prompt.  
它不是 LoRA，也不会改写你的 Prompt。

Its purpose is to help H3 keep complex action relationships clearer.  
它的作用是帮助 H3 在复杂动作里更稳定地保持人物、动作、目标、物体和前后状态之间的关系。

---

## ✨ What does it improve?
## ✨ 它主要改进什么？

Complex action can sometimes cause H3 to lose track of who is doing what.  
复杂动作里，H3 有时会搞不清谁在做什么。

Typical problems include:  
常见问题包括：

- **Actions jumping from one character to another.**  
  **动作从一个人串到另一个人。**

- **Weapons or objects changing owner.**  
  **武器或道具突然换主人。**

- **Attacker / target relationships becoming confused.**  
  **攻击者和目标关系混乱。**

- **Identity relationships breaking after turning, crossing, or occlusion.**  
  **转身、换位、遮挡以后人物关系丢失。**

- **The next action continuing from the wrong previous state.**  
  **后一个动作从错误的前一状态继续。**

BUNNY_H3_Conditioning_Bridge is designed to reduce these failures.  
BUNNY_H3_Conditioning_Bridge 主要就是针对这些问题。

---

## ⚔️ Recommended combinations
## ⚔️ 推荐搭配

I currently recommend using it together with **COMBAT V2** or **Motion Continuity Repair LoRA**.  
目前推荐和 **COMBAT V2** 或 **动作连续性修复 LoRA** 一起使用。

```text
COMBAT V2 / Motion Continuity Repair
→ how the action moves and continues
→ 负责动作怎么打、怎么接、怎么保持连续

Semantic Bridge V1
→ who is doing what and which state belongs to whom
→ 负责谁在做什么、动作和状态到底属于谁
```

This is especially useful in complex multi-character scenes such as **1-vs-4 combat**.  
在 **1 对 4** 这种复杂多人场景里尤其有帮助。

It can help keep the scene more stable when several characters move, exchange positions, attack, react, or occlude each other.  
多人同时移动、换位、攻击、受击、互相遮挡时，它能帮助 H3 更稳定地保持场景关系。

---

## 📦 Installation
## 📦 安装

### 1. Custom node
### 1. 自定义节点

Put:  
把：

```text
BUNNY_H3_Conditioning_Bridge
```

into:  
放到：

```text
ComfyUI/custom_nodes/
```

Then restart ComfyUI.  
然后重启 ComfyUI。

---

### 2. Model
### 2. 模型文件

Model:  
模型：

```text
BUNNY_H3_ActionLogic_Bridge_V1.safetensors
```

Recommended folder:  
推荐目录：

```text
ComfyUI/custom_nodes/BUNNY_H3_Conditioning_Bridge/models/
```
## If installed through ComfyUI Manager, the folder name may appear as bunny-h3-semantic-bridge. This is normal.
## 如果通过 ComfyUI Manager 安装，节点文件夹名称可能会显示为 bunny-h3-semantic-bridge，这是正常的。

## The node does not depend on a fixed folder name. Just place the Bridge model inside the models folder of the actual installed node directory.
## 节点并不依赖固定的文件夹名称，只需要把 Bridge 模型放进你实际安装的节点目录中的 models 文件夹即可。

例如：

ComfyUI/custom_nodes/BUNNY_H3_Conditioning_Bridge/models/

或者：

ComfyUI/custom_nodes/bunny-h3-semantic-bridge/models/

Both are valid.
两种都可以。
---

## ⚙️ Usage
## ⚙️ 使用方法

Use the node:  
使用节点：

```text
BUNNY H3 Conditioning Bridge
```

Recommended starting settings:  
推荐起始参数：

```text
alpha = 0.10 ~ 0.15
magnitude_match = per_token
enabled = true
```

Start low and test with the same seed.  
建议从低强度开始，并使用同一个 Seed 做对比。

Higher strength is not automatically better.  
强度并不是越高越好。

---
## 🔌 Where should the node be connected?
## 🔌 节点应该接在哪里？

The Bridge must be placed **after the MiniMax H3 text-conditioning encoder**.  
Bridge 必须放在 **MiniMax H3 文本 Conditioning 编码完成之后**。

The easiest way to use it is to find the existing `CONDITIONING` cable in your H3 workflow, disconnect it, insert the Bridge in the middle, and reconnect the Bridge output to the original downstream node.  
最简单的用法就是：找到你 H3 工作流里原本那根 `CONDITIONING` 线，把它断开，把 Bridge 插在中间，再把 Bridge 输出重新接回原来的下游节点。

```text
BEFORE / 原来：

H3 Text / Prompt Conditioning
        │
        │ CONDITIONING
        ▼
Original downstream node
原来的下游节点


AFTER / 加入 Bridge 后：

H3 Text / Prompt Conditioning
        │
        │ CONDITIONING
        ▼
BUNNY H3 Conditioning Bridge
        │
        │ CONDITIONING
        ▼
Original downstream node
原来的下游节点
```

In simple terms:  
简单来说：

```text
H3 Conditioning
→ BUNNY H3 Conditioning Bridge
→ Original downstream node
```

```text
H3 Conditioning
→ BUNNY H3 Conditioning Bridge
→ 原来要接的下游节点
```

**Do not connect the Bridge to `MODEL`, `LoRA`, `LATENT`, `VAE`, image, or audio lines.**  
**不要把 Bridge 接到 `MODEL`、`LoRA`、`LATENT`、`VAE`、图片或音频线路上。**

It only receives and outputs `CONDITIONING`.  
它只接收并输出 `CONDITIONING`。

If your workflow already works normally without the Bridge, you do not need to rebuild the workflow. Just insert the Bridge into the existing H3 `CONDITIONING` connection.  
如果你的工作流本来就可以正常运行，不需要重新搭工作流，只需要把 Bridge 插进现有的 H3 `CONDITIONING` 线路中间即可。
---
## 📊 Current test observations
## 📊 当前测试观察

In my current test set, about **60%** of cases showed different levels of repair or improvement.  
在我目前的测试里，大约 **60%** 的案例出现了不同程度的修复或增益。

About **20%** showed no obvious difference between Bridge OFF and Bridge ON.  
大约 **20%** 的案例在 Bridge OFF / ON 之间没有明显差别。

Around **10%** produced new errors or regressions after enabling the Bridge.  
大约 **10%** 的案例在开启 Bridge 后会出现新的错误或退化。

These are approximate observations from my current tests, not a formal benchmark or guaranteed success rate.  
这些数字只是目前测试中的大致观察，不是正式 Benchmark，也不代表固定成功率。

Because these are approximate field observations rather than a normalized statistical report, the percentages are not intended to sum exactly to 100%.  
因为这是实际测试中的近似观察，而不是严格归一化的统计报告，所以这些比例不要求精确相加等于 100%。


## 📥 Model links
## 📥 模型地址

**Semantic Bridge V1 and work flow:**  
**Semantic Bridge V1 和工作流：**

https://huggingface.co/JOKER141/BUNNY_H3_Conditioning_Bridge

**COMBAT V2:**  
**COMBAT V2：**

https://huggingface.co/JOKER141/MiniMax-H3-Combat-Base-V2

**Motion Continuity Repair LoRA:**  
**动作连续性修复 LoRA：**

https://huggingface.co/JOKER141/MiniMax-H3-General-Motion-Continuity-Repair

---

## 🙏 Original project
## 🙏 原项目

This project was originally inspired by **speach1sdef178 / MiniMax-H3-Semantic-Bridge**.  
这个项目最早受 **speach1sdef178 / MiniMax-H3-Semantic-Bridge** 启发。

Thanks to the original author for publicly sharing the research idea, code, data, and experiments.  
感谢原作者公开研究思路、代码、数据和实验过程。

Original project:  
原项目：

https://huggingface.co/speach1sdef178/MiniMax-H3-Semantic-Bridge

---

> **The LoRA helps H3 perform the motion. Semantic Bridge V1 helps H3 keep track of who is doing what while the scene gets complicated.**  
> **LoRA 负责让 H3 把动作做出来，Semantic Bridge V1 负责场景复杂以后，尽量别搞丢谁在干什么。**

**FourBunny / JOKER141**
