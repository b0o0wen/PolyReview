# PolyReview ⚖️（多模型交叉评审）

<!-- TODO(P2): social preview 卡图 (1280x640): 跨厂商评审员 3 轮收敛 -->

[![CI](https://github.com/b0o0wen/PolyReview/actions/workflows/ci.yml/badge.svg)](https://github.com/b0o0wen/PolyReview/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

**让你的 AI 编程 agent 互相评审。** 把任意组合的 CLI agent —— Claude Code、Codex、Gemini、Qwen、Kimi、OpenCode、Aider… —— 组成交叉评审团，对你的技术方案与代码 diff 多轮质询，直到收敛。

> 单个模型自评是循环论证。**不同厂商的模型交叉质询你的设计文档，才是真评审。**（一家评审员即可与 host 形成交叉；2-3 家不同厂商时交叉验证最强）

<!-- TODO(P2): GIF 演示 — host 模式: 两家厂商独立命中同一问题(交叉验证的名场面), host 仲裁, verdict JSON, 收敛 -->

## 为什么

- **跨厂商交叉验证**：不同模型家族的评审员独立定位同一缺陷的概率远超偶然 —— 真实会话中出现过 3 个轮次的重复命中（[方法论与实证数据](docs/methodology.md)）
- **收敛而非发散**：verdict 协议（`APPROVE`/`REVISE` + 分级 issues）+ host 仲裁人 —— 真实会话 2-4 轮收敛
- **该有状态时有状态**：每位评审员跨轮续聊自己的会话（记得自己提过什么），失效自动降级新会话 —— 正确性从不依赖记忆
- **评审员 = agent，不是模型**：你选哪些 CLI 上评审席，模型由各 CLI 自带配置决定。`polyreview scan` 探测本机装了哪些

## 30 秒上手（零 API 成本）

```bash
# npx / pnpx（JS 用户：薄壳启动器，Python 后端首次运行自动装）
npx polyreview demo

# uvx（Python 用户最快；PyPI 发布后: `uvx polyreview demo`）
uvx --from git+https://github.com/b0o0wen/PolyReview.git polyreview demo

# 或传统方式
curl -fsSL https://raw.githubusercontent.com/b0o0wen/PolyReview/main/install.sh | sh
pip install git+https://github.com/b0o0wen/PolyReview.git

polyreview demo      # mock 评审团: REVISE → 处置 → APPROVE，无需任何 key
polyreview init --host claude   # 一条命令: MCP 评审员 + skill 装进你的 host
```

> 前置条件：**至少一个与 host 模型家族不同的评审员 CLI** 已安装并登录。一家评审员即可交叉质询你的 host agent；2-3 家不同厂商时交叉验证最强（`polyreview scan` 查看本机情况）。

## 实际使用

```bash
polyreview scan                      # 本机装了哪些评审员 CLI？
polyreview init --host claude        # 打印每位评审员的 claude mcp add 命令
polyreview init --host qoder --write .vscode/mcp.json --reviewers kimi,codex

# batch: 对方案(或导出的 git diff)跑一轮交叉评审
polyreview review --artifact docs/design.md --reviewers kimi,codex --mode spec
git diff main...HEAD > review_state/pr/change.diff
polyreview review --artifact review_state/pr/change.diff --mode code
```

或在 MCP host（Qoder / Claude Code / Cursor / VS Code）里驱动 —— **主模式**：host agent 仲裁（起草采纳/反驳处置，你签字），评审员交叉质询。每位评审员是标准 MCP server，暴露 `review(request, session_id, cwd)`、`identity()`、`whereami()` 三工具；随包的 [skill](polyreview/skills/polyreview/SKILL.md) 让你说一句"多模型交叉评审"即可触发。上面的 batch CLI 是 CI/脚本补充（退出码 0 = 全票 APPROVE），不是第二前端 —— 见 [ROADMAP](ROADMAP.md)。

## 支持的评审员

按常见度排序：

| Agent | 状态 | 续聊 |
|-------|------|------|
| claude (Claude Code) | 已实测 | ✅ `--resume` |
| codex (Codex CLI) | 已实测 | ✅ `exec resume` |
| gemini (Gemini CLI) | 实验性 | ✅ `--resume`（据文档） |
| qwen (Qwen Code) | 已实测 | ✅ `--resume`（全链路实测） |
| kimi (Kimi Code) | 已实测 | ✅ `kimi -r` |
| opencode | 语法已验证 | ✅ `run -s` |
| aider | 实验性 | —（设计上无状态） |
| qoder | 实验性 | — |

其他 CLI 通过 `reviewers.toml` 接入（命令模板 + 会话 id 正则）—— 见 [registry 文档](polyreview/registry.py)。实验性适配器欢迎 PR 验证；每个被验证的 adapter 都带着它社区的祝福上线。

## 工作原理

```
        ┌─ reviewer-kimi ──┐   verdict JSON
作者 ───┤                  ├──► host 仲裁人 ── 采纳 / 反驳 ──► 下一轮
        └─ reviewer-codex ─┘   (blocker/major 阻塞; minor 不阻塞)    │
                                                                     ▼
                                            全票 APPROVE / 达轮数上限
```

完整协议与实证数据：[docs/methodology.md](docs/methodology.md) · host 兼容性踩坑实录（MCP roots、stdin 继承、structuredContent 不透传）见 [docs/host-compat.md](docs/host-compat.md)。

## 状态

Alpha。已在两个 host（Qoder、Claude Code）上以 kimi+codex 日常使用验证；实验性适配器待社区验证。MIT。

English version: [README.en.md](README.en.md)
