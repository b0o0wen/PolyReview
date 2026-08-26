"""内置评审员注册表 + TOML 自定义扩展。

内置 6 个 agent 适配器（用户只选 agent，不选模型）：
  - codex / claude / kimi：已实测（续聊链路验证通过）
  - qoder / trae / opencode：实验性（命令模板来自公开文档，未实测）
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
        name="qoder", binary="qoder",
        new_cmd=["qoder", "-p", "{prompt}"],
        experimental=True,
        notes="实验性：本机未安装，headless 参数按公开文档推断，待社区验证。",
    ),
    Adapter(
        name="trae", binary="trae",
        new_cmd=["trae", "-p", "{prompt}"],
        experimental=True,
        notes="实验性：本机未安装，待社区验证（Trae CLI）。",
    ),
    Adapter(
        name="opencode", binary="opencode",
        new_cmd=["opencode", "run", "{prompt}"],
        experimental=True,
        notes="实验性：本机未安装。opencode run 为 headless 模式，续聊参数待验证。",
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
