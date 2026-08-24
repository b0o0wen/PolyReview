"""Reviewer adapter: 把任意 CLI agent 变成交叉评审团成员。

抽象极简：一个 adapter = new/resume 命令模板 + 会话 id 提取规则。
用户只选 agent，不选模型 —— 模型由各 CLI 自身配置决定（identity 工具自检实际模型）。

三个用实测换来的实现铁律（详见 docs/host-compat.md）：
1. 子进程必须 stdin=DEVNULL：CLI 继承 MCP 协议管道会永久挂起（codex 实测卡 15 分钟）
2. 会话提示行位置因 CLI 而异：kimi/codex 在 stderr，claude 在 stdout JSON —— 两处都搜
3. 续聊失败（无输出）自动降级新会话，正确性不依赖会话记忆（请求永远带全量上下文）
"""

import json
import re
import subprocess
from dataclasses import dataclass, field


@dataclass
class Adapter:
    name: str
    binary: str                      # doctor 用：探测是否安装
    new_cmd: list[str]               # 含 '{prompt}' 占位符
    resume_cmd: list[str] | None = None    # 含 '{prompt}' '{session}'；None=该 CLI 无续聊
    session_regex: str | None = None       # group(1) = 会话 id，在 stderr+stdout 上搜索
    session_from_stdout_json: bool = False # claude: stdout 是 JSON，取 session_id 字段
    timeout: int = 3600
    experimental: bool = False       # 未实测验证
    notes: str = ""
    binary_hints: list[str] = field(default_factory=list)  # 非标准安装路径探测

    def build(self, prompt: str, session: str | None) -> list[str]:
        tpl = self.resume_cmd if (session and self.resume_cmd) else self.new_cmd
        return [a.replace("{session}", session or "").replace("{prompt}", prompt) for a in tpl]

    def extract_session(self, stdout: str, stderr: str) -> str:
        if self.session_from_stdout_json:
            try:
                return str(json.loads(stdout).get("session_id") or "")
            except (json.JSONDecodeError, ValueError):
                pass
        if self.session_regex:
            m = re.search(self.session_regex, (stderr or "") + "\n" + (stdout or ""), re.MULTILINE)
            if m:
                return m.group(1)
        return ""

    def run(self, prompt: str, session: str | None, cwd: str | None) -> tuple[str, str, int]:
        """执行一次评审。返回 (stdout, stderr, returncode)。超时抛 subprocess.TimeoutExpired。"""
        proc = subprocess.run(
            self.build(prompt, session),
            capture_output=True, text=True, timeout=self.timeout, cwd=cwd,
            stdin=subprocess.DEVNULL,  # 铁律 1：切断继承的 MCP stdin，防 CLI 挂起
        )
        return (proc.stdout or "").strip(), (proc.stderr or "").strip(), proc.returncode

    def review(self, prompt: str, session: str | None, cwd: str | None) -> dict:
        """带续聊降级的评审调用：返回 {reply, stderr, session_id, resumed}。"""
        attempts = ([session] if session else []) + [None]  # 续聊优先，新会话兜底
        last_err = ""
        for sess in attempts:
            try:
                out, err, rc = self.run(prompt, sess, cwd)
            except subprocess.TimeoutExpired:
                last_err = f"超时（>{self.timeout}s）"
                continue
            if not out:
                last_err = f"无输出 rc={rc} stderr={err[:300]}"
                continue  # 续聊失效或瞬时失败 → 下一 attempt
            sid = self.extract_session(out, err)
            return {"reply": out, "stderr": err, "session_id": sid,
                    "resumed": sess is not None}
        return {"reply": f"[{self.name}] {last_err}", "stderr": "",
                "session_id": "", "resumed": False}
