"""PolyReview CLI 入口。

命令：
  polyreview demo [--mock]      零成本演示完整评审循环（mock 评审员）
  polyreview doctor             探测已安装的评审员 CLI + 实验性警告
  polyreview init --host H      生成 MCP 接入配置（qoder/claude/cursor/vscode）
  polyreview review ...         batch 模式：并行送审一轮，落盘 verdicts/sessions
"""

import argparse
import json
import os
import sys

from . import __version__
from .registry import REGISTRY, discover_installed, get_adapter

_PY = sys.executable


def _server_cmd(name: str) -> list[str]:
    return [_PY, "-m", "polyreview.server", name]


def cmd_init(args) -> int:
    names = [n.strip() for n in args.reviewers.split(",") if n.strip()]
    entries = {}
    for n in names:
        entries[f"reviewer-{n}"] = {"type": "stdio",
                                    "command": _PY,
                                    "args": ["-m", "polyreview.server", n]}
    host = args.host
    if host == "qoder":
        cfg = {"mcp": {"servers": entries}}          # 用户级 settings.json 追加；工作区级为 .vscode/mcp.json 的 {"servers": ...}
    elif host == "claude":
        print("# 逐条执行：")
        for n in names:
            argv = " ".join(_server_cmd(n))
            print(f'claude mcp add --scope user reviewer-{n} -- {argv}')
        return 0
    elif host in ("cursor", "vscode"):
        key = "mcpServers" if host == "cursor" else "servers"
        cfg = {key: entries}
        if host == "vscode":
            print("# 写入工作区 .vscode/mcp.json")
    else:
        raise SystemExit(f"未知 host: {host}（支持 qoder/claude/cursor/vscode）")
    if args.write:
        os.makedirs(os.path.dirname(args.write) or ".", exist_ok=True)
        with open(args.write, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"已写入 {args.write}")
    else:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args) -> int:
    print(f"polyreview {__version__} — 评审员 CLI 探测：\n")
    for a, ok in discover_installed():
        line = f"  {'✅' if ok else '⬜'} {a.name:<10}"
        if a.experimental:
            line += "（实验性：命令模板未实测）"
        print(line + f"  {a.notes[:60]}")
    print("\n✅=已安装可直接用  ⬜=未安装（安装对应 CLI 后即可）")
    return 0


def cmd_demo(args) -> int:
    from .engine import demo
    return demo()


def cmd_review_impl(args) -> int:
    from .engine import run_round, all_approve
    names = [n.strip() for n in args.reviewers.split(",") if n.strip()]
    adapters = {n: get_adapter(n) for n in names}
    state = args.state_dir or os.path.join("review_state", args.slug or "artifact")
    prior, log = {}, ""
    if args.round > 1:
        prev = os.path.join(state, f"round_{args.round - 1}")
        sp = os.path.join(prev, "sessions.json")
        if os.path.exists(sp):
            prior = {n: i.get("session_id") for n, i in json.load(open(sp)).items()
                     if i.get("session_id")}
        dp = os.path.join(prev, "host_disposition.md")
        if os.path.exists(dp):
            log = open(dp, encoding="utf-8").read()
    verdicts, _ = run_round(adapters, os.path.abspath(args.artifact),
                            os.path.join(state, f"round_{args.round}"),
                            mode=args.mode, cwd=args.cwd, prior_sessions=prior,
                            review_log=log)
    if all_approve(verdicts):
        print("\n全票 APPROVE ✅")
        return 0
    print(f"\n未全票：处置 blocker/major 后写 host_disposition.md，再 --round {args.round + 1}")
    return 1


def main() -> None:
    p = argparse.ArgumentParser(prog="polyreview",
                                description="多 agent 交叉评审：让任意 CLI agent 互相评审方案与代码")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="零成本演示（mock）").set_defaults(func=cmd_demo)

    sub.add_parser("doctor", help="探测已安装的评审员 CLI").set_defaults(func=cmd_doctor)

    pi = sub.add_parser("init", help="生成 MCP 接入配置")
    pi.add_argument("--host", required=True, choices=["qoder", "claude", "cursor", "vscode"])
    pi.add_argument("--reviewers", default="kimi,codex", help="逗号分隔（默认 kimi,codex）")
    pi.add_argument("--write", default=None, help="写入目标文件路径（默认打印）")
    pi.set_defaults(func=cmd_init)

    pr = sub.add_parser("review", help="batch 送审一轮")
    pr.add_argument("--artifact", required=True, help="评审对象文件（方案 md 或导出的 diff）")
    pr.add_argument("--reviewers", default="kimi,codex")
    pr.add_argument("--mode", default="spec", choices=["spec", "code"])
    pr.add_argument("--round", type=int, default=1)
    pr.add_argument("--slug", default=None, help="状态目录名（默认 artifact）")
    pr.add_argument("--state-dir", default=None)
    pr.add_argument("--cwd", default=None, help="评审员工作目录（默认当前目录）")
    pr.set_defaults(func=cmd_review_impl)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
