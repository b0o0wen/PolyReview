# PolyReview ⚖️ 多模型交叉评审

<!-- TODO(P2): social preview 卡图 (1280x640): 跨厂商评审员 3 轮收敛 -->

[![CI](https://github.com/b0o0wen/PolyReview/actions/workflows/ci.yml/badge.svg)](https://github.com/b0o0wen/PolyReview/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

**让你的 AI 编程 agent 互相评审。** Claude Code、Codex、Gemini、Qwen、Kimi、OpenCode、Aider……随便挑几个 CLI agent 组成评审团，对你的技术方案和代码改动反复挑刺，挑到全员点头为止。

> 自己写的代码自己评，等于没评。**换几家不同厂商的模型来互相挑刺，才算真评审。** 哪怕只有一个评审员，它和你 host 里的模型也是两家，交叉就已经成立；凑够两三家不同厂商，效果最佳。

<!-- TODO(P2): GIF 演示 — host 模式: 两家厂商独立命中同一问题(交叉验证的名场面), host 仲裁, verdict JSON, 收敛 -->

## 为什么用它

- **跨厂商才叫交叉**：不同厂商的模型各有各的盲区，却会撞出同样的缺陷——真实评审里，两位评审员曾连续三轮各自独立发现同一个问题（[方法论与实证](docs/methodology.md)）
- **有始有终，不会评起来没完**：评审结论是一份结构化的 verdict（`APPROVE`/`REVISE` 加分级问题清单），host 负责逐条裁决，真实评审一般 2-4 轮收尾
- **记得住，但也不怕失忆**：每位评审员跨轮沿用同一个会话，记得自己上轮提过什么；万一会话失效，自动换新会话重来，评审结果从不依赖这份记忆
- **选的是 agent，不是模型**：你只需决定哪些 CLI 坐上评审席，用什么模型由各 CLI 自己的配置说了算。跑 `polyreview scan` 就知道本机有哪些可用

## 30 秒上手（不用花一分钱）

```bash
# JS 用户：npx 即可，Python 后端首次运行时自动安装
npx polyreview demo

# Python 用户：uvx 最省事（PyPI 发布后可直接 `uvx polyreview demo`）
uvx --from git+https://github.com/b0o0wen/PolyReview.git polyreview demo

# 传统安装
curl -fsSL https://raw.githubusercontent.com/b0o0wen/PolyReview/main/install.sh | sh
pip install git+https://github.com/b0o0wen/PolyReview.git

polyreview demo      # 演示模式：mock 评审团走完 提意见→改方案→通过 全流程，不需要任何 key
polyreview init --host claude   # 一条命令，把 MCP 评审员和 skill 装进你的 host
```

> 前提只有一个：**本机至少装了一个评审员 CLI，且它背后的模型和你 host 不是一家**。装好登录好，`polyreview scan` 一看便知。

## 日常怎么用

```bash
polyreview scan                      # 本机装了哪些评审员 CLI？
polyreview init --host claude        # 生成每位评审员的 claude mcp add 命令
polyreview init --host qoder --write .vscode/mcp.json --reviewers kimi,codex

# 命令行批处理：对一份方案（或导出的 git diff）跑一轮交叉评审
polyreview review --artifact docs/design.md --reviewers kimi,codex --mode spec
git diff main...HEAD > review_state/pr/change.diff
polyreview review --artifact review_state/pr/change.diff --mode code
```

更常用的方式是在 MCP host（Qoder / Claude Code / Cursor / VS Code）里直接说句话——这是**主模式**：评审员互相挑刺，你的 host agent 出面仲裁（替你拟好每条意见的采纳或反驳，由你拍板）。每位评审员都是一个标准 MCP server，提供 `review(request, session_id, cwd)`、`identity()`、`whereami()` 三个工具；配套 [skill](polyreview/skills/polyreview/SKILL.md) 装好后，一句"多模型交叉评审"就能触发。上面的命令行批处理主要给 CI 和脚本用（退出码 0 即全票通过），定位是补充而非另一套前端——详见 [ROADMAP](ROADMAP.md)。

## 支持哪些评审员

按常见程度排序：

| Agent | 状态 | 续聊 |
|-------|------|------|
| claude (Claude Code) | 已实测 | ✅ `--resume` |
| codex (Codex CLI) | 已实测 | ✅ `exec resume` |
| gemini (Gemini CLI) | 实验性 | ✅ `--resume`（据文档） |
| qwen (Qwen Code) | 已实测 | ✅ `--resume`（全链路实测） |
| kimi (Kimi Code) | 已实测 | ✅ `kimi -r` |
| opencode | 语法已验证 | ✅ `run -s` |
| aider | 实验性 | —（设计上无状态） |
| qodercli | 实验性 | —（续聊待验证） |

不在这个列表里的 CLI 也能接：写一段 `reviewers.toml`（命令模板加一条会话 id 正则）就行，见 [registry 文档](polyreview/registry.py)。实验性适配器欢迎各位装了对应 CLI 的朋友实测提 PR——每一条被验证过的适配器，都算社区共同背书。

## 工作原理

```
        ┌─ reviewer-kimi ──┐   verdict JSON
作者 ───┤                  ├──► host 仲裁 ── 采纳 / 反驳 ──► 下一轮
        └─ reviewer-codex ─┘   (blocker/major 挡住; minor 只记录)  │
                                                                    ▼
                                          全票 APPROVE / 到达轮数上限
```

协议细节与实证数据见 [docs/methodology.md](docs/methodology.md)；各 host 的兼容性坑（MCP roots、stdin 继承、structuredContent 不透传）都记在 [docs/host-compat.md](docs/host-compat.md)。

## 项目状态

Alpha。作者日常在 Qoder 和 Claude Code 两个 host 上以 kimi+codex 高频使用；实验性适配器等大家来验证。MIT 协议。

English version: [README.en.md](README.en.md)
