# PolyReview ⚖️（多模型交叉评审）

让任意 CLI agent（Codex / Claude Code / Kimi / Qoder / Trae / OpenCode...）互相评审你的技术方案与代码 diff，直到全票通过。

单个模型自评是循环论证；**两个不同厂商的模型交叉质询你的方案，才叫评审团。**

## 快速开始

```bash
pip install -e .
polyreview demo                          # 零成本 mock 演示：REVISE → 处置 → APPROVE
polyreview doctor                        # 探测本机已装的评审员 CLI
polyreview init --host qoder             # 一键生成 MCP 接入配置
polyreview review --artifact 方案.md --reviewers kimi,codex
```

设计理念与协议见 [README.md](README.md)（英文主文档）与 [docs/methodology.md](docs/methodology.md)。
MIT License。评审员 = agent（不选模型），实验性适配器（qoder/trae/opencode）欢迎社区验证提 PR。
