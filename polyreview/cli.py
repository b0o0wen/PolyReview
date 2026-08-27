"""PolyReview CLI 入口。

命令：
  polyreview demo               零成本演示完整评审循环（mock 评审员）
  polyreview scan             探测已安装的评审员 CLI + 实验性警告
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

# Host 注册表（数据驱动）：title/desc/skill_dir + mcp 接入方式。
# mcp 形态：("cmd", 命令模板{server}{argv}) / ("json", 默认路径, 顶层key, None) / ("toml", 路径) / None(skill-only)
HOSTS = {
    "claude": {"title": "Claude Code", "desc": "终端里的 Claude Code CLI，`claude` 命令启动",
               "skill_dir": "~/.claude/skills",
               "mcp": ("cmd", "claude mcp add --scope user {server} -- {argv}")},
    "qoder": {"title": "Qoder", "desc": "字节的 AI IDE（QoderCN）",
              "skill_dir": "~/.qoder-cn/skills",
              "mcp": ("json", ".vscode/mcp.json", "servers", None)},
    "cursor": {"title": "Cursor", "desc": "Cursor 编辑器（AI IDE）",
               "skill_dir": "~/.cursor/skills",
               "mcp": ("json", ".cursor/mcp.json", "mcpServers", None)},
    "vscode": {"title": "VS Code", "desc": "Visual Studio Code（Copilot/Continue 生态）",
               "skill_dir": "~/.continue/skills",
               "mcp": ("json", ".vscode/mcp.json", "servers", None)},
    "zcode": {"title": "zcode", "desc": "zcode CLI（.zcode）",
               "skill_dir": "~/.zcode/skills", "mcp": None,
               "note": "实测暂无 MCP 注册能力；skill 已验证可用（驱动 CLI 批处理路径）"},
    "codex": {"title": "Codex CLI", "desc": "Codex 既是评审员也能当 host（agent 会话里用）",
               "skill_dir": None,
               "mcp": ("toml", "~/.codex/config.toml", None, None)},
    "gemini": {"title": "Gemini CLI", "desc": "Gemini CLI 同样可作 host（gemini mcp 官方命令）",
                "skill_dir": None,
                "mcp": ("cmd", "gemini mcp add {server} {argv}")},
    "qwen": {"title": "Qwen Code", "desc": "Qwen Code 同样可作 host（qwen mcp 官方命令）",
              "skill_dir": None,
              "mcp": ("cmd", "qwen mcp add {server} {argv}")},
    "opencode": {"title": "OpenCode", "desc": "OpenCode 同样可作 host（opencode mcp）",
                  "skill_dir": None, "experimental": True,
                  "mcp": ("cmd", "opencode mcp add {server} -- {argv}")},
    "windsurf": {"title": "Windsurf", "desc": "Codeium Windsurf 编辑器",
                  "skill_dir": None, "experimental": True,
                  "mcp": ("json", "~/.codeium/windsurf/mcp_config.json", "mcpServers", None)},
}


def _print_host_menu() -> None:
    """列出全部 host 的说明表（选单/报错教学共用）。"""
    print("  host 选哪个？看你在哪个工具里和 AI 对话：\n")
    for i, (h, spec) in enumerate(HOSTS.items(), 1):
        flag = " [实验性]" if spec.get("experimental") else ""
        print(f"  {i}. {h:<9} {spec['title']} — {spec['desc']}{flag}")
    print()


def _pick_host(arg_host: str | None) -> str:
    """--host 缺省 → 交互选单；非法值 → 报错并展示说明表（把报错变成教学）。"""
    if arg_host is None:
        print("── PolyReview 一键接入 ──")
        _print_host_menu()
        choice = input(f"选择序号（1-{len(HOSTS)}）或直接回车退出: ").strip()
        if not choice:
            raise SystemExit("未选择 host，退出（可重跑: polyreview init --host <name>）")
        hosts = list(HOSTS)
        try:
            return hosts[int(choice) - 1]
        except (ValueError, IndexError):
            raise SystemExit(f"无效选择 '{choice}'；直接指定: polyreview init --host <{'/'.join(hosts)}>")
    if arg_host not in HOSTS:
        print(f"✗ 未知 host '{arg_host}'\n")
        _print_host_menu()
        raise SystemExit(f"用法: polyreview init --host <{'/'.join(HOSTS)}>\n"
                         f"或不带 --host 进入选单: polyreview init")
    return arg_host


def _install_skill(host: str) -> str | None:
    """把随包分发的 skill 复制到 host 的技能目录（仅支持已确认目录约定的 host）。"""
    skill_dir = HOSTS[host].get("skill_dir")
    if not skill_dir or not os.path.isdir(_SKILL_SRC):
        return None
    dst_root = os.path.expanduser(skill_dir)
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


def _pick_reviewers(arg_reviewers: str | None, loaded: dict) -> list[str]:
    """--reviewers 缺省 → 交互多选（含安装状态与实验性提示）；已指定则直接解析。

    多选语法：空格分隔序号（如 "1 3"）；all = 全选；回车 = 接受默认评审团。
    列表含内置 + config 自定义项；未安装的 CLI 可选但给警告（用户可能计划后续安装）。
    """
    installed = {a.name for a, ok in discover_installed() if ok}
    customs = {c["name"] for c in loaded["reviewers"]}
    default = loaded["panel"]["reviewers"]

    if arg_reviewers:
        names = [n.strip() for n in arg_reviewers.split(",") if n.strip()]
    else:
        print("\n评审团选哪些 agent？（交叉验证的前提：不同厂商）\n")
        options = list(REGISTRY) + sorted(customs - set(REGISTRY))
        for i, n in enumerate(options, 1):
            a = REGISTRY.get(n)
            marks = "✅ 已装" if n in installed else ("⬜ 未装" if a else "⚙ 自定义")
            extra = " ·实验性未实测" if (a and a.experimental) else ""
            print(f"  {i}. {n:<10} {marks}{extra}")
        print(f"  回车 = 默认评审团（{', '.join(default)}）")
        raw = input("选择（空格分隔序号，如 \"1 3\"；all=全选）: ").strip()
        if not raw:
            return list(default)
        if raw.lower() == "all":
            return options
        try:
            names = [options[int(x) - 1] for x in raw.split()]
        except (ValueError, IndexError):
            raise SystemExit(f"无效选择 '{raw}'（示例: 1 3 或 all；也可 --reviewers kimi,codex）")

    # 校验（两种入口共用）
    for n in names:
        if n not in REGISTRY and n not in customs:
            raise SystemExit(f"未知评审员 '{n}'（内置: {sorted(REGISTRY)}；自定义进 config.toml）")
    missing = [n for n in names if n not in installed and n not in customs]
    if missing:
        print(f"  ⚠ 未安装: {', '.join(missing)}（可继续，先用已装的；装好 CLI 后即可用）")
    chosen = [n for n in names if n in installed or n in customs] or list(names)
    return chosen


def cmd_init(args) -> int:
    loaded = config.load(args.config)
    host = _pick_host(args.host)
    h = HOSTS[host]
    names = _pick_reviewers(args.reviewers, loaded)
    cfg_path = loaded["source"]          # 有配置文件则让 server 启动时读同一份

    print(f"── PolyReview 一键接入 → {h['title']} ──")
    if h.get("experimental"):
        print("（实验性 host：配置格式来自公开文档，未实测）")

    # [1/2] MCP 按接入方式分发
    mcp = h.get("mcp")
    print("\n[1/2] MCP 评审员")
    if mcp is None:
        print(f"  跳过：{h.get('note', '该 host 暂不支持 MCP 注册')}；skill 将驱动 CLI 批处理路径")
    else:
        kind = mcp[0]
        if kind == "cmd":
            for n in names:
                argv = " ".join(_server_cmd(n, cfg_path))
                print("  " + mcp[1].format(server=f"reviewer-{n}", argv=argv))
            print("  ↑ 逐条复制执行（官方 CLI 命令，幂等可重复）")
        elif kind == "json":
            target = os.path.expanduser(args.write or mcp[1])
            entries = {}
            for n in names:
                entries[f"reviewer-{n}"] = {"type": "stdio", "command": _PY,
                                            "args": ["-m", "polyreview.server", n] + ([cfg_path] if cfg_path else [])}
            body = {mcp[2]: entries}
            os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(body, f, ensure_ascii=False, indent=2)
            print(f"  已写入 {target}（{', '.join(names)}）")
        elif kind == "toml":
            target = os.path.expanduser(args.write or mcp[1])
            existing = open(target).read() if os.path.exists(target) else ""
            with open(target, "a", encoding="utf-8") as f:
                for n in names:
                    if f"[mcp_servers.reviewer-{n}]" in existing:
                        print(f"  跳过已存在: reviewer-{n}")
                        continue
                    f.write(f"\n[mcp_servers.reviewer-{n}]\ncommand = \"{_PY}\"\n")
                    f.write("args = " + json.dumps(["-m", "polyreview.server", n]
                                                    + ([cfg_path] if cfg_path else [])) + "\n")
            print(f"  已追加到 {target}（{', '.join(names)}）")

    # [2/2] Skill
    print("\n[2/2] Skill")
    try:
        dst = _install_skill(host)
    except OSError as exc:
        dst = None
        print(f"  ⚠ skill 安装失败（{exc}）；MCP 已可用，可手动复制 {_SKILL_SRC} → {HOSTS[host].get('skill_dir')}")
    if dst:
        print(f"  已安装 → {dst}")
    elif HOSTS[host].get("skill_dir") is None:
        print("  该 host 无已验证的 skill 目录约定，跳过（MCP 工具可直接调用）")
    if dst:
        print("\n完成 ✅  重载 host（Reload Window / 重启会话）后说：\n"
              "  中文: \"多模型交叉评审 <方案/diff>\"   EN: \"cross-review <spec/diff>\"")
    else:
        print("\n完成 ✅  重启 host 会话后即可使用 MCP 评审员工具")
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


def cmd_scan(args) -> int:
    print(f"polyreview {__version__} — 评审员 CLI 扫描：\n")
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
    sub.add_parser("scan", help="扫描已装的评审员 CLI + 当前配置").set_defaults(func=cmd_scan)

    pi = sub.add_parser("init", help="一键安装：MCP 配置 + skill（不带 --host 进选单）")
    pi.add_argument("--host", default=None,
                    help=f"目标 host：{'/'.join(HOSTS)}（缺省进交互选单）")
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
