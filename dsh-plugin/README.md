# dsh-headless-resume

给 dsh headless 加上 `--resume` 续聊能力 —— PolyReview 项目的 dsh 适配器组件。

## 问题

dsh 的 headless profile 是 one-shot：每次调用都创建新会话，没有 `--resume` 参数。
tui profile 有 `--resume` 但为交互式 TUI，不适合非交互场景（CI、MCP adapter、脚本）。

## 方案

本包是 `@deepseek-ai/dsh-headless` 的 drop-in 替代，新增：

- `--resume <uuid>` — 加载持久化会话并在其上继续对话
- 完成后在 stderr 打印 `dsh: session: <uuid>` — 供下次 resume 用

底层调用 dsh 内部的 `agents.resume({ resumeSessionId })` API（源码验证存在，
`dsh-agent-loop/lib/index.js:1876`），与 tui 的续聊机制同一条路径。

## 安装

```bash
# 1. 创建一个基于 headless 的自定义 profile
dsh --profile headless-resume --from-default-profile headless

# 2. 安装本插件（从 git 或本地路径）
dsh plugin --profile headless-resume add @b0o0wen/polyreview --filter dsh-plugin
# 或本地路径：
dsh plugin --profile headless-resume add ./dsh-plugin
```

## 使用

```bash
# 新会话（与原 headless 相同）
dsh --profile headless-resume "分析这个方案"
# stderr: dsh: session: 40248dc0-321b-4ae5-872b-9e841dea2857

# 续聊（新能力！）
dsh --profile headless-resume --resume 40248dc0-321b-4ae5-872b-9e841dea2857 "上一个问题改了，请重新看"
```

## PolyReview adapter 对接

安装本插件后，在 PolyReview 的 reviewers.toml 中：

```toml
[[reviewer]]
name = "dsh"
new_cmd = ["dsh", "--profile", "headless-resume", "{prompt}"]
resume_cmd = ["dsh", "--profile", "headless-resume", "--resume", "{session}", "{prompt}"]
session_regex = 'dsh: session:\s*([0-9a-f-]{36})'
```

## 注意

- 本插件需要 dsh ≥ 0.1.5-rc.1（`agents.resume()` API 稳定版本）
- 首次使用 `headless-resume` profile 时自动初始化
- 会话持久化在 `~/.dsh/sessions/<workspace>/<uuid>/`，与 tui 的数据互通
