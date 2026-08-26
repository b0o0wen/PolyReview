"""内置评审员注册表 + TOML 自定义扩展。

内置 6 个 agent 适配器（用户只选 agent，不选模型）：
  - codex / claude / kimi：已实测（续聊链路验证通过）
  - gemini / aider / qodercli：实验性（qwen 已语法实测）（命令模板来自公开文档，未实测）
自定义 reviewer 用 TOML 声明，例如：

    [[reviewer]]
    name = "aider"
    new_cmd = ["aider", "--message", "{prompt}", "--yes-always"]
    session_regex = 'session (\\S+)'
"""

import os

try:
    import tomllib
except ImportError:  # py<3.11
    tomllib = None

from .adapter import Adapter

REGISTRY: dict[str, Adapter] = {a.name: a for a in [
    Adapter(
        name="kimi", binary="kimi",
        binary_hints=["~/.kimi-code/bin/kimi"],
        new_cmd=["kimi", "-p", "{prompt}"],
        resume_cmd=["kimi", "-r", "{session}", "-p", "{prompt}"],
        session_regex=r"To resume this session: kimi -r (\S+)",
        notes="Kimi K3（月之暗面）。stdout 是干净回复，resume 提示行在 stderr。",
    ),
    Adapter(
        name="codex", binary="codex",
        new_cmd=["codex", "exec", "--skip-git-repo-check", "{prompt}"],
        resume_cmd=["codex", "exec", "resume", "--skip-git-repo-check", "{session}", "{prompt}"],
        session_regex=r"^session id:\s*([0-9a-f-]+)",
        notes="OpenAI Codex CLI。模型跟随 ~/.codex/config.toml 或登录态（曾实测漂移；"
              "如需钉死可在 new_cmd/resume_cmd 加 -c model=...，配合 identity 自检）。",
    ),
    Adapter(
        name="claude", binary="claude",
        new_cmd=["claude", "-p", "{prompt}", "--output-format", "json"],
        resume_cmd=["claude", "--resume", "{session}", "-p", "{prompt}", "--output-format", "json"],
        session_from_stdout_json=True,
        notes="Claude Code CLI。模型跟随订阅/env（注意：部分 host 环境注入的 "
              "ANTHROPIC_BASE_URL 会把它路由到其他厂商端点，用 identity 自检核实）。",
    ),
    Adapter(
        name="qodercli", binary="qodercli",
        new_cmd=["qodercli", "-p", "{prompt}", "-o", "json"],
        session_regex=r'"session_id"\s*:\s*"([^"]+)"',
        experimental=True,
        notes="Qoder CLI（字节）。headless: qodercli -p；-o json 结构化输出含 session_id"
              "（据 qodercli-mcp 社区项目文档，该包装器即以 qodercli -p 驱动）。"
              "续聊参数待本机实测后补。命令名是 qodercli（不是 qoder）。",
    ),
    Adapter(
        name="opencode", binary="opencode",
        binary_hints=["~/.opencode/bin/opencode"],
        new_cmd=["opencode", "run", "{prompt}"],
        resume_cmd=["opencode", "run", "-s", "{session}", "{prompt}"],
        session_regex=r'"sessionID"\s*:\s*"(ses_[^"]+)"',
        notes="OpenCode（SST）。headless = opencode run；续聊 -s <id>；"
              "sessionID 在 JSON 事件流（ses_ 前缀）。模型跟随 opencode providers 配置。"
              "命令语法已实测（1.18.23），评审回复链路待有效 key 验证。",
    ),
    Adapter(
        name="gemini", binary="gemini",
        new_cmd=["gemini", "-p", "{prompt}", "--output-format", "json"],
        resume_cmd=["gemini", "--resume", "{session}", "-p", "{prompt}",
                    "--output-format", "json"],
        session_regex=r'"session_id"\s*:\s*"([0-9a-f-]{36})"',
        experimental=True,
        notes="Google Gemini CLI。headless: gemini -p --output-format json；续聊 --resume <uuid>。"
              "已实测(0.57.0): JSON 输出在 stderr(stdout 为空), session_id 在 JSON 顶层;"
              "未登录时也返回 session_id+error(rc=41), 提取链路已验证; 回复链路待有效 key。",
    ),
    Adapter(
        name="qwen", binary="qwen",
        new_cmd=["qwen", "-p", "{prompt}", "--output-format", "json"],
        resume_cmd=["qwen", "--resume", "{session}", "-p", "{prompt}",
                    "--output-format", "json"],
        session_regex=r'"session_id"\s*:\s*"([0-9a-f-]{36})"',
        experimental=False,
        notes="阿里 Qwen Code（fork 自 Gemini CLI）。headless: qwen -p --output-format json；"
              "续聊 --resume <uuid> -p；会话存 ~/.qwen/projects/<cwd>/chats。"
              "全链路已实测(0.22.2, 第三方 provider 真实调用): JSON 在 stdout, regex 提取 ok,"
              "续聊 --resume 同 id 贯穿且记住上轮内容; OAuth 免费 tier 已停(2026-04),"
              "第三方 provider 需在 ~/.qwen/settings.json 配置(无需 CLI 参数)。",
    ),
    Adapter(
        name="aider", binary="aider",
        new_cmd=["aider", "--message", "{prompt}", "--yes-always", "--no-git"],
        experimental=True,
        notes="Aider（老牌 pair-programmer）。headless: aider --message；"
              "会话历史在 .aider.chat.history.md（无 stdout 会话 id），故不配续聊"
              "（每次新会话，请求携带全量上下文，正确性不受影响）。未本机实测。",
    ),
]}


def get_adapter(name: str, config_path: str | None = None) -> Adapter:
    """按名取 adapter；config_path 的 TOML 自定义项优先于内置。"""
    if config_path:
        if tomllib is None:
            raise RuntimeError("自定义 reviewer 配置需要 Python 3.11+（tomllib）")
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        for item in data.get("reviewer", []):
            if item.get("name") == name:
                item.setdefault("binary", item["new_cmd"][0])
                return Adapter(**item)
    if name in REGISTRY:
        return REGISTRY[name]
    raise KeyError(f"未知评审员 '{name}'。内置: {sorted(REGISTRY)}；自定义见 registry 模块文档")


def discover_installed() -> list[tuple[Adapter, bool]]:
    """探测哪些评审员 CLI 已安装（scan 用）。返回 [(adapter, installed)]。"""
    import shutil
    found = []
    for a in REGISTRY.values():
        ok = shutil.which(a.binary) is not None or any(
            os.path.exists(os.path.expanduser(h)) for h in a.binary_hints
        )
        found.append((a, ok))
    return found
