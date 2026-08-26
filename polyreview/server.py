"""通用 MCP server 工厂：`python -m polyreview.server <reviewer-name>` 启动一个评审员。

与 adapter 解耦：任何注册表里的 agent（含 TOML 自定义）都能一键变成 MCP server。
工具（对任意 host 语义一致）：
  review(request, session_id="", cwd="")  → {reply, session_id, resumed, cwd}
  identity()                              → 评审员身份卡（含模型跟随说明）
  whereami(cwd="")                        → 工作目录解析自检（不调模型）

注意：cwd 解析链 = 显式参数 → MCP roots → env POLYREVIEW_CWD → 进程 cwd（带工程标记）。
部分 host（如 Qoder）不提供 roots 且不透传 structuredContent，故返回值走明文 JSON。
"""

import os
import sys
from urllib.parse import unquote, urlparse

from mcp.server.fastmcp import Context, FastMCP

from .registry import get_adapter

_MARKERS = (".git", "package.json", "pyproject.toml", "go.mod", "Cargo.toml",
            "setup.py", "requirements.txt", "pom.xml")


def _looks_like_workspace(path: str) -> bool:
    return any(os.path.exists(os.path.join(path, m)) for m in _MARKERS)


async def _resolve_cwd(ctx: Context, explicit: str = "") -> tuple[str, str]:
    if explicit and os.path.isdir(explicit):
        return explicit, "param:cwd"
    try:
        result = await ctx.session.list_roots()
        for root in result.roots:
            uri = str(root.uri)
            if uri.startswith("file://"):
                path = unquote(urlparse(uri).path)
                if os.path.isdir(path):
                    return path, "roots"
    except Exception:
        pass
    env_cwd = os.environ.get("POLYREVIEW_CWD", "")
    if env_cwd and os.path.isdir(env_cwd):
        return env_cwd, "env:POLYREVIEW_CWD"
    proc_cwd = os.getcwd()
    if _looks_like_workspace(proc_cwd):
        return proc_cwd, "process-cwd"
    return "", "unset"


def create_server(adapter, server_name: str | None = None) -> FastMCP:
    mcp = FastMCP(server_name or f"reviewer-{adapter.name}")

    @mcp.tool()
    async def review(request: str = "", session_id: str = "", cwd: str = "",
                     ctx: Context = None) -> dict:
        """送审：request 为完整评审请求（工件给绝对路径，不内嵌全文）。

        无 session_id 新会话；带则续聊，失效自动降级（resumed=false）。
        cwd 传调用方当前工作区绝对路径（评审员在该目录读代码）。
        """
        if not request:
            return {"reply": f"[{adapter.name}] request 不能为空（工件给绝对路径，不内嵌）",
                    "session_id": "", "resumed": False, "cwd": cwd or ""}
        resolved, source = await _resolve_cwd(ctx, cwd)
        out = adapter.review(request, session_id or None, resolved or None)
        return {"reply": out["reply"], "session_id": out["session_id"],
                "resumed": out["resumed"],
                "cwd": f"{resolved}（来源: {source}）" if resolved else "unset"}

    @mcp.tool()
    def identity() -> str:
        """评审员身份卡：agent 名 / 续聊能力 / 模型跟随说明。"""
        resume = "支持 session_id 续聊，失效自动降级" if adapter.resume_cmd else "无续聊（每次新会话）"
        flag = " [实验性，未实测]" if adapter.experimental else ""
        return (f"评审员: {adapter.name}{flag} | 续聊: {resume} | "
                f"模型: 由 {adapter.binary} CLI 自身配置决定（评审员=agent，不选模型） | "
                f"备注: {adapter.notes}")

    @mcp.tool()
    async def whereami(cwd: str = "", ctx: Context = None) -> dict:
        """工作目录解析自检（不调模型）。返回 {cwd, source}。"""
        resolved, source = await _resolve_cwd(ctx, cwd)
        return {"cwd": resolved, "source": source,
                "hint": "source 非 param:cwd 时，请在 review 调用中显式传 cwd"}

    return mcp


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("用法: python -m polyreview.server <reviewer-name> [reviewers.toml]")
    adapter = get_adapter(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    create_server(adapter).run()  # stdio


if __name__ == "__main__":
    main()
