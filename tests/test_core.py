"""核心测试：verdict 解析 / adapter 命令构建与会话提取 / mock 循环收敛 / 配置生成。

全部零模型成本（mock + 纯函数），可直接进 CI。
运行: python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tribunal.adapter import Adapter
from tribunal.engine import parse_verdict, blocking_issues, all_approve, run_round
from tribunal.mock import MockAdapter
from tribunal.registry import REGISTRY, get_adapter


class TestVerdict(unittest.TestCase):
    def test_json_block(self):
        text = '总体可行。\n```json\n{"verdict": "REVISE", "issues": [{"id":1,"severity":"major","point":"p","suggestion":"s"}], "summary":"x"}\n```'
        v = parse_verdict(text)
        self.assertEqual(v["verdict"], "REVISE")
        self.assertTrue(v["parse_ok"])
        self.assertEqual(len(blocking_issues(v)), 1)

    def test_last_block_wins(self):
        text = '```json\n{"verdict":"APPROVE","issues":[]}\n``` 然后 ```json\n{"verdict":"REVISE","issues":[]}\n```'
        self.assertEqual(parse_verdict(text)["verdict"], "REVISE")

    def test_no_block_falls_back(self):
        v = parse_verdict("模型没按协议输出")
        self.assertEqual(v["verdict"], "REVISE")
        self.assertFalse(v["parse_ok"])

    def test_minor_not_blocking(self):
        v = {"issues": [{"severity": "minor"}]}
        self.assertEqual(blocking_issues(v), [])


class TestAdapters(unittest.TestCase):
    def test_kimi_session_from_stderr(self):
        a = REGISTRY["kimi"]
        self.assertEqual(
            a.extract_session("", "To resume this session: kimi -r session_abc123"),
            "session_abc123")

    def test_codex_session_from_header(self):
        a = REGISTRY["codex"]
        self.assertEqual(a.extract_session("", "session id: 01a0-ff\nuser"), "01a0-ff")

    def test_claude_session_from_json(self):
        a = REGISTRY["claude"]
        out = json.dumps({"session_id": "s-1", "result": "ok"})
        self.assertEqual(a.extract_session(out, ""), "s-1")

    def test_build_templates(self):
        a = REGISTRY["codex"]
        self.assertIn("resume", " ".join(a.build("P", "S")))
        self.assertNotIn("resume", " ".join(a.build("P", None)))

    def test_custom_toml(self):
        path = "/tmp/_tribunal_test_reviewers.toml"
        open(path, "w").write(
            '[[reviewer]]\nname = "echo"\nnew_cmd = ["echo", "{prompt}"]\n')
        a = get_adapter("echo", path)
        self.assertEqual(a.binary, "echo")


class TestMockLoop(unittest.TestCase):
    def test_two_round_convergence(self):
        import tempfile
        adapters = {"m1": MockAdapter("m1"), "m2": MockAdapter("m2")}
        with tempfile.TemporaryDirectory() as d:
            v1, s1 = run_round(adapters, "/dev/null/x", os.path.join(d, "r1"))
            self.assertFalse(all_approve(v1))
            v2, _ = run_round(adapters, "/dev/null/x", os.path.join(d, "r2"),
                              review_log="已采纳",
                              prior_sessions={n: i["session_id"] for n, i in s1.items()})
            self.assertTrue(all_approve(v2))
            # 第二轮必须续聊（mock session id 稳定）
            sessions2 = json.load(open(os.path.join(d, "r2", "sessions.json")))
            self.assertTrue(all(i["resumed"] for i in sessions2.values()))


if __name__ == "__main__":
    unittest.main()
