"""确定性 mock 评审员：零成本体验完整评审循环（demo 命令 + CI 测试后端）。

行为：首轮 REVISE（固定意见），复核轮 APPROVE（收敛），演示"3 轮内收敛"的完整语义。
"""

import itertools

from .adapter import Adapter

_counter = itertools.count(1)


class MockAdapter(Adapter):
    def __init__(self, name: str = "mock"):
        super().__init__(
            name=name, binary="",
            new_cmd=["mock://{prompt}"], resume_cmd=["mock://{session}/{prompt}"],
            session_regex=None, timeout=10,
            notes="确定性 mock 评审员：首轮 REVISE、复核轮 APPROVE（零模型成本）",
        )
        self._sid = f"mock-session-{next(_counter)}"

    def run(self, prompt: str, session: str | None, cwd: str | None):
        re_review = ("复核" in prompt) or (session is not None)
        if re_review:
            out = ("处置已核实，无新阻塞问题。\n```json\n"
                   '{"verdict": "APPROVE", "issues": [], "summary": "mock: 收敛通过"}\n```')
        else:
            out = ("发现一个阻塞问题：mock 评审员要求增加失败模式说明。\n```json\n"
                   '{"verdict": "REVISE", "issues": [{"id": 1, "severity": "major", '
                   '"point": "缺少失败模式章节", "suggestion": "补充失败模式与恢复"}], '
                   '"summary": "mock: 首轮意见"}\n```')
        return out, "", 0

    def extract_session(self, stdout: str, stderr: str) -> str:
        return self._sid
