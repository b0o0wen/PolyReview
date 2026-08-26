"""配置中心：唯一配置入口 ~/.config/polyreview/config.toml（项目级 .polyreview.toml 覆盖）。

配置一次，两条消费路径（MCP server / batch CLI）统一生效：
  [panel]      reviewers / max_rounds / timeout —— 评审团与循环默认值
  [[reviewer]] 自定义评审员（与内置同字段，覆盖同名内置项）

发现链：项目 ./.polyreview.toml > ~/.config/polyreview/config.toml > 内置默认。
CLI 显式参数（--reviewers/--config 等）优先于配置文件。
"""

import os

try:
    import tomllib
except ImportError:  # py<3.11
    tomllib = None

DEFAULTS = {"reviewers": ["kimi", "codex"], "max_rounds": 20, "timeout": 3600}

TEMPLATE = """\
# PolyReview 配置。改完对 MCP 路径需重载 host；batch 路径即时生效。
[panel]
# 评审团成员（内置: claude/codex/gemini/qwen/kimi/opencode/aider/qoder；自定义见下方 [[reviewer]]）
reviewers = ["kimi", "codex"]
# 循环上限（host 驱动的自动循环护栏；batch 为单轮驱动不受限）
max_rounds = 20
# 单次评审超时秒数（全仓评审耗时长属正常）
timeout = 3600

# 自定义评审员示例（命令模板 + 会话提取；session/resume 可选）
# [[reviewer]]
# name = "aider"
# new_cmd = ["aider", "--message", "{prompt}", "--yes-always"]
# resume_cmd = ["aider", "--resume", "{session}", "--message", "{prompt}"]
# session_regex = 'session (\\S+)'
"""


def user_config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "polyreview", "config.toml")


def find_config(explicit: str | None = None) -> str | None:
    """显式路径 > 项目 ./.polyreview.toml > 用户级。返回存在的路径或 None。"""
    if explicit:
        return explicit
    for p in (os.path.join(os.getcwd(), ".polyreview.toml"), user_config_path()):
        if os.path.isfile(p):
            return p
    return None


def load(explicit: str | None = None) -> dict:
    """返回 {panel: {...}, reviewers: [自定义 reviewer dict...], source: 路径}。"""
    path = find_config(explicit)
    panel, customs = dict(DEFAULTS), []
    if path and tomllib is not None:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        panel.update({k: v for k, v in data.get("panel", {}).items()
                      if k in DEFAULTS})
        customs = list(data.get("reviewer", []))
    elif path:
        raise RuntimeError("配置文件需要 Python 3.11+（tomllib）")
    return {"panel": panel, "reviewers": customs, "source": path}


def write_template(path: str | None = None) -> str:
    """生成配置模板（默认用户级路径）。已存在则不动，返回路径。"""
    target = path or user_config_path()
    if not os.path.exists(target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(TEMPLATE)
        print(f"已生成配置模板: {target}")
    else:
        print(f"配置已存在（未覆盖）: {target}")
    return target


def set_value(key: str, value: str, path: str | None = None) -> None:
    """set 面板项：panel.reviewers / panel.max_rounds / panel.timeout。

    path 缺省时按发现链定位（项目级 > 用户级；都没有则生成用户级模板）。
    """
    target = path or find_config() or user_config_path()
    if not os.path.exists(target):
        write_template(target)
    lines = open(target, encoding="utf-8").read().splitlines(keepends=True)
    k = key.removeprefix("panel.")
    rendered = f'{k} = {json_like(value)}'
    out, replaced = [], False
    in_panel = False
    for ln in lines:
        if ln.strip() == "[panel]":
            in_panel = True
        elif ln.startswith("[") and ln.strip() != "[panel]":
            in_panel = False
        if in_panel and not replaced and (ln.strip().startswith(k + " ") or ln.strip().startswith(k + "=")):
            out.append(rendered + "\n")
            replaced = True
        else:
            out.append(ln)
    if not replaced:  # panel 段里没有该键 → 追加到段尾
        for i in range(len(out) - 1, -1, -1):
            if out[i].strip() == "[panel]":
                out.insert(i + 1, rendered + "\n")
                break
        else:
            out.insert(0, "[panel]\n" + rendered + "\n")
    open(target, "w", encoding="utf-8").writelines(out)
    print(f"已设置 {key} = {value}（{target}）")


def json_like(value: str) -> str:
    """把 CLI 值渲染成 toml 字面量：列表按逗号拆，数字裸写，其余字符串。"""
    if "," in value:
        items = ", ".join(f'"{x.strip()}"' for x in value.split(",") if x.strip())
        return f"[{items}]"
    if value.isdigit():
        return value
    return f'"{value}"'


def add_reviewer(name: str, new_cmd: str, resume_cmd: str | None = None,
                 session_regex: str | None = None, path: str | None = None) -> None:
    """追加一个 [[reviewer]] 到配置文件（纯文本追加，可读可手改）。

    new_cmd/resume_cmd 为 shell 风格字符串（含 {prompt}/{session} 占位），shlex 拆成数组。
    """
    import shlex
    target = path or find_config() or user_config_path()
    if not os.path.exists(target):
        write_template(target)
    lines = ["", "[[reviewer]]", f'name = "{name}"',
             "new_cmd = " + _toml_array(shlex.split(new_cmd))]
    if resume_cmd:
        lines.append("resume_cmd = " + _toml_array(shlex.split(resume_cmd)))
    if session_regex:
        lines.append(f"session_regex = '{session_regex}'")
    with open(target, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"已添加评审员 {name} → {target}\n"
          f"启用：polyreview config set reviewers <,...{name},...> 或 init --reviewers 含 {name}")


def _toml_array(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"
