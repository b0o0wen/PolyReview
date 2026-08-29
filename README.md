# PolyReview ⚖️ 多模型交叉评审

<!-- TODO(P2): social preview 卡图 (1280x640): 跨厂商评审员 3 轮收敛 -->

[![CI](https://github.com/b0o0wen/PolyReview/actions/workflows/ci.yml/badge.svg)](https://github.com/b0o0wen/PolyReview/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

**让你的 AI 编程 agent 互相评审。** 从 Claude Code、Codex、Gemini、Qwen、Kimi、OpenCode、Aider 等 CLI agent 中任选若干组成评审团，对技术方案与代码变更进行多轮独立评审，直至全体通过。

> 模型评审自己的输出，无法跳出自身的盲区。**由不同厂商的模型和 agent 交叉评审，评审更加有效。** 只有一个评审员时，它与 host 模型仍属不同厂商，交叉已经成立；两到三家不同厂商时，交叉验证效果最佳。

<!-- TODO(P2): GIF 演示 — host 模式: 两家厂商独立命中同一问题(交叉验证的关键镜头), host 仲裁, verdict JSON, 收敛 -->

## 为什么用它

- **跨厂商交叉验证**：不同厂商的模型盲区各异，却能独立发现相同缺陷——真实评审中，两位评审员曾连续三轮各自命中同一个问题（[方法论与实证数据](docs/methodology.md)）
- **收敛而非发散**：评审结论是结构化的 verdict（`APPROVE`/`REVISE` 加分级问题清单），由 host 逐条裁决，真实评审通常 2-4 轮收敛
- **会话可续，但不依赖**：每位评审员跨轮沿用同一会话，记得自己上轮提出的意见；会话失效时自动降级为新会话，评审结果从不依赖这份记忆
- **选 agent，不选模型**：只需决定哪些 CLI 进入评审团，所用模型由各 CLI 自身的配置决定。`polyreview scan` 可探测本机可用的评审员

## 30 秒上手（零 API 成本）

```bash
# JS 用户：npx 即可，Python 后端在首次运行时自动安装
npx polyreview demo

# Python 用户：uvx 最便捷（PyPI 发布后可直接 `uvx polyreview demo`）
uvx --from git+https://github.com/b0o0wen/PolyReview.git polyreview demo

# 常规安装
curl -fsSL https://raw.githubusercontent.com/b0o0wen/PolyReview/main/install.sh | sh
pip install git+https://github.com/b0o0wen/PolyReview.git

polyreview demo      # 演示模式：mock 评审团完整走一遍 提出意见 → 修改 → 通过，无需任何 key
polyreview init --host claude   # 一条命令，将 MCP 评审员与 skill 安装到你的 host
```

> 前提只有一条：**本机至少安装了一个评审员 CLI，且其背后的模型与你的 host 不同厂商**。安装登录后，运行 `polyreview scan` 即可确认。

## 日常使用

```bash
polyreview scan                      # 本机安装了哪些评审员 CLI？
polyreview init --host claude        # 生成每位评审员的 claude mcp add 命令
polyreview init --host qoder --write .vscode/mcp.json --reviewers kimi,codex

# 命令行批处理：对一份方案（或导出的 git diff）执行一轮交叉评审
polyreview review --artifact docs/design.md --reviewers kimi,codex --mode spec
git diff main...HEAD > review_state/pr/change.diff
polyreview review --artifact review_state/pr/change.diff --mode code
```

更常用的方式是在 MCP host（Qoder / Claude Code / Cursor / VS Code）中直接发起——这是**主模式**：评审员各自独立评审，host agent 负责仲裁（为每条意见起草采纳或反驳方案，由你确认）。每位评审员都是一个标准 MCP server，提供 `review(request, session_id, cwd)`、`identity()`、`whereami()` 三个工具；配套 [skill](polyreview/skills/polyreview/SKILL.md) 安装后，一句"多模型交叉评审"即可触发。命令行批处理面向 CI 与脚本场景（退出码 0 即全票通过），定位是主模式的补充而非另一套前端——详见 [ROADMAP](ROADMAP.md)。

## 支持的评审员

按常见程度排序：

| Agent | 状态 | 续聊 |
|-------|------|------|
| claude (Claude Code) | 已实测 | ✅ `--resume` |
| codex (Codex CLI) | 已实测 | ✅ `exec resume` |
| gemini (Gemini CLI) | 实验性 | ✅ `--resume`（据文档） |
| qwen (Qwen Code) | 已实测 | ✅ `--resume`（全链路实测） |
| kimi (Kimi Code) | 已实测 | ✅ `kimi -r` |
| opencode | 已实测 | ✅ `run -s`（全链路实测，NDJSON） |
| aider | 实验性 | —（设计上无状态） |
| qodercn | 已实测 | ✅ `-r`（全链路实测） |
| qoder | 实验性 | ✅ `-r`（语法已验证，待登录） |

列表之外的 CLI 同样可以接入：编写一段 `reviewers.toml`（命令模板加一条会话 id 提取正则）即可，详见 [registry 文档](polyreview/registry.py)。欢迎安装了对应 CLI 的用户实测并提交 PR，每一个通过验证的适配器都由社区共同背书。

## 工作原理

```
        ┌─ reviewer-kimi ──┐   verdict JSON
作者 ───┤                  ├──► host 仲裁 ── 采纳 / 反驳 ──► 下一轮
        └─ reviewer-codex ─┘   (blocker/major 阻塞; minor 仅记录)   │
                                                                      ▼
                                            全票 APPROVE / 达到轮数上限
```

协议细节与实证数据见 [docs/methodology.md](docs/methodology.md)；各 host 的兼容性问题（MCP roots、stdin 继承、structuredContent 不透传）记录于 [docs/host-compat.md](docs/host-compat.md)。

## 项目状态

Alpha。已在 Qoder 与 Claude Code 两个 host 上以 kimi+codex 日常使用验证；实验性适配器待社区验证。MIT 协议。

English version: [README.en.md](README.en.md)
