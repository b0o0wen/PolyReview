"""PolyReview CLI 入口。

命令：
  polyreview demo               零成本演示完整评审循环（mock 评审员）
  polyreview doctor             探测已安装的评审员 CLI + 实验性警告
  polyreview init --host H      一键安装：MCP 配置 + skill（qoder/claude/cursor/vscode）
  polyreview config [...]       配置中心：查看/生成模板/设置 panel 项
  polyreview review ...         batch 模式：并行送审一轮，落盘 verdicts/sessions
"""

import argparse
import json
import os
import shutil
import sys

from . import __version__, config
from .registry import REGISTRY, discover_installed, get_adapter

_PY = sys.executable
# skill 随包分发（打包进 wheel，pip 安装后 init 可用）
_SKILL_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "skills", "polyreview")

# 各 host 的 skill 安装目录（个人全局）
_SKILL_DIRS = {
    "qoder": "~/.qoder-cn/skills",
    "claude": "~/.claude/skills",
    "cursor": "~/.cursor/skills",
    "vscode": "~/.continue/skills",
}
_SKILL_NAMES = {"qoder": "Qoder", "claude": "Claude Code", "cursor": "Cursor", "vscode": "VS Code"}


def _install_skill(host: str) -> str | None:
    """把随包分发的 skill 复制到 host 的技能目录（目标目录名 = polyreview，无重复 review）。"""
    dst_root = os.path.expanduser(_SKILL_DIRS[host])
    if not os.path.isdir(_SKILL_SRC):
        return None
    dst = os.path.join(dst_root, "polyreview")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(_SKILL_SRC, dst)
    return dst


def _server_cmd(name: str, cfg_path: str | None) -> list[str]:
    argv = [_PY, "-m", "polyreview.server", name]
    if cfg_path:
        argv += [cfg_path]
    return argv


def cmd_init(args) -> int:
    loaded = config.load(args.config)
    names = ([n.strip() for n in args.reviewers.split(",")] if args.reviewers
             else loaded["panel"]["reviewers"])
    for n in names:
        if n not in REGISTRY and n not in {c.get("name") for c in loaded["reviewers"]}:
            raise SystemExit(f"未知评审员 '{n}'（内置: {sorted(REGISTRY)}；自定义进 config.toml）")
    cfg_path = loaded["source"]          # 有配置文件则让 server 启动时读同一份
    host = args.host
    entries = {}
    for n in names:
        entries[f"reviewer-{n}"] = {"type": "stdio", "command": _PY,
                                    "args": ["-m", "polyreview.server", n] + ([cfg_path] if cfg_path else [])}

    print(f"── PolyReview 一键安装 → {_SKILL_NAMES[host]} ──\n[1/2] MCP 评审员")
    if host == "claude":
        for n in names:
            print(f"  claude mcp add --scope user reviewer-{n} -- " +
                  " ".join(_server_cmd(n, cfg_path)))
    else:
        target = args.write or {("qoder"): ".vscode/mcp.json",
                                "cursor": ".cursor/mcp.json",
                                "vscode": ".vscode/mcp.json"}[host]
        key = "servers" if host in ("qoder", "vscode") else "mcpServers"
        body = {key: entries}
        if host == "qoder":
            body = {"servers": entries}   # 工作区 .vscode/mcp.json 形态；用户级套 {"mcp": body}
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        print(f"  已写入 {target}（{', '.join(names)}）")

    print("[2/2] Skill")
    dst = _install_skill(host)
    if dst:
        print(f"  已安装 → {dst}")
        print("\n完成 ✅  重载 host（Reload Window / 重启会话）后说：\n"
              "  中文: \"多模型交叉评审 <方案/diff>\"   EN: \"cross-review <spec/diff>\"")
    else:
        print("  ⚠ skill 源缺失（skills/polyreview-review），跳过；MCP 已可用")
    if cfg_path:
        print(f"\n配置文件（两路径共用）: {cfg_path}")
    return 0


def cmd_config(args) -> int:
    if args.config_cmd == "init":
        config.write_template(args.path)
        return 0
    if args.config_cmd == "set":
        key = args.key
        if "." not in key:            # 裸键（max_rounds 5）等价 panel.max_rounds
            key = f"panel.{key}"
        config.set_value(key, args.value)
        return 0
    if args.config_cmd == "add-reviewer":
        config.add_reviewer(args.name, args.new, args.resume, args.session_regex)
        return 0
    loaded = config.load()
    print(f"来源: {loaded['source'] or '内置默认（未发现配置文件）'}")
    print(json.dumps(loaded["panel"], ensure_ascii=False, indent=2))
    if loaded["reviewers"]:
        print(f"自定义评审员: {[r.get('name') for r in loaded['reviewers']]}（config add-reviewer 可再加）")
    return 0


def cmd_doctor(args) -> int:
    print(f"polyreview {__version__} — 评审员 CLI 探测：\n")
    for a, ok in discover_installed():
        line = f"  {'✅' if ok else '⬜'} {a.name:<10}"
        if a.experimental:
            line += "（实验性：命令模板未实测）"
        print(line + f"  {a.notes[:60]}")
    loaded = config.load()
    print(f"\n评审团默认: {', '.join(loaded['panel']['reviewers'])}"
          f"（max_rounds={loaded['panel']['max_rounds']}, timeout={loaded['panel']['timeout']}s）"
          f"\n配置来源: {loaded['source'] or '内置默认'}")
    return 0


def cmd_demo(args) -> int:
    from .engine import demo
    return demo()


def cmd_review_impl(args) -> int:
    from .engine import run_round, all_approve
    loaded = config.load(args.config)
    names = ([n.strip() for n in args.reviewers.split(",")] if args.reviewers
             else loaded["panel"]["reviewers"])
    customs = {c["name"]: c for c in loaded["reviewers"]}
    adapters = {}
    for n in names:
        if n in customs:
            item = dict(customs[n]); item.setdefault("binary", item["new_cmd"][0])
            from .adapter import Adapter
            adapters[n] = Adapter(**item)
        else:
            adapters[n] = get_adapter(n)
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
    for a in adapters.values():
        a.timeout = loaded["panel"]["timeout"]
    verdicts, _ = run_round(adapters, os.path.abspath(args.artifact),
                            os.path.join(state, f"round_{args.round}"),
                            mode=args.mode, cwd=args.cwd, prior_sessions=prior,
                            review_log=log)
    if all_approve(verdicts):
        print("\n全票 APPROVE ✅")
        return 0
    print(f"\n未全票：处置 blocker/major 后写 host_disposition.md，再 --round {args.round + 1}"
          f"（max_rounds={loaded['panel']['max_rounds']}）")
    return 1


def main() -> None:
    p = argparse.ArgumentParser(prog="polyreview",
                                description="多模型交叉评审：让任意 CLI agent 互相评审方案与代码")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="零成本演示（mock）").set_defaults(func=cmd_demo)
    sub.add_parser("doctor", help="探测评审员 CLI + 当前配置").set_defaults(func=cmd_doctor)

    pi = sub.add_parser("init", help="一键安装：MCP 配置 + skill")
    pi.add_argument("--host", required=True, choices=["qoder", "claude", "cursor", "vscode"])
    pi.add_argument("--reviewers", default=None, help="逗号分隔（默认取 config panel.reviewers）")
    pi.add_argument("--write", default=None, help="MCP 配置写入路径（默认按 host 约定）")
    pi.add_argument("--config", default=None, help="显式配置文件路径")
    pi.set_defaults(func=cmd_init)

    pc = sub.add_parser("config", help="配置中心")
    pcs = pc.add_subparsers(dest="config_cmd")
    pcs.add_parser("show", help="查看生效配置").set_defaults(func=cmd_config)
    pinit = pcs.add_parser("init", help="生成配置模板")
    pinit.add_argument("--path", default=None)
    pinit.set_defaults(func=cmd_config)
    pset = pcs.add_parser("set", help="设置 panel 项（裸键即可：max_rounds 5 / reviewers kimi,codex）")
    pset.add_argument("key"); pset.add_argument("value")
    pset.set_defaults(func=cmd_config)
    padd = pcs.add_parser("add-reviewer", help="添加自定义评审员到配置（写入 [[reviewer]]）")
    padd.add_argument("name", help="评审员名（如 aider）")
    padd.add_argument("--new", required=True,
                      help="新建会话命令模板，引号包住，含 {prompt}（如 'aider --message {prompt} --yes-always'）")
    padd.add_argument("--resume", default=None, help="续聊命令模板，含 {session} {prompt}")
    padd.add_argument("--session-regex", default=None, help="从输出提取会话 id 的正则（group 1）")
    padd.set_defaults(func=cmd_config)
    pc.set_defaults(func=cmd_config, config_cmd="show")

    pr = sub.add_parser("review", help="batch 送审一轮")
    pr.add_argument("--artifact", required=True, help="评审对象文件（方案 md 或导出的 diff）")
    pr.add_argument("--reviewers", default=None, help="逗号分隔（默认取 config）")
    pr.add_argument("--mode", default="spec", choices=["spec", "code"])
    pr.add_argument("--round", type=int, default=1)
    pr.add_argument("--slug", default=None, help="状态目录名（默认 artifact）")
    pr.add_argument("--state-dir", default=None)
    pr.add_argument("--cwd", default=None, help="评审员工作目录（默认当前目录）")
    pr.add_argument("--config", default=None, help="显式配置文件路径")
    pr.set_defaults(func=cmd_review_impl)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
