"""核心测试：verdict 解析 / adapter 命令构建与会话提取 / mock 循环收敛 / 配置生成。

全部零模型成本（mock + 纯函数），可直接进 CI。
运行: python -m unittest discover -s tests -v
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polyreview.adapter import Adapter
from polyreview.engine import parse_verdict, blocking_issues, all_approve, run_round
from polyreview.mock import MockAdapter
from polyreview.registry import REGISTRY, get_adapter


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

    def test_opencode_session_from_json_event(self):
        a = REGISTRY["opencode"]
        out = '{"type":"message","sessionID":"ses_fc1184f9","text":"ok"}'
        self.assertEqual(a.extract_session(out, ""), "ses_fc1184f9")

    def test_claude_session_from_json(self):
        a = REGISTRY["claude"]
        out = json.dumps({"session_id": "s-1", "result": "ok"})
        self.assertEqual(a.extract_session(out, ""), "s-1")

    def test_build_templates(self):
        a = REGISTRY["codex"]
        self.assertIn("resume", " ".join(a.build("P", "S")))
        self.assertNotIn("resume", " ".join(a.build("P", None)))

    def test_custom_toml(self):
        path = "/tmp/_polyreview_test_reviewers.toml"
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


class TestConfig(unittest.TestCase):
    def test_load_chain_and_customs(self):
        import tempfile
        from polyreview import config as cfg
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.toml")
            open(p, "w").write(
                '[panel]\nmax_rounds = 5\n\n'
                '[[reviewer]]\nname = "echo"\nnew_cmd = ["echo", "{prompt}"]\n')
            loaded = cfg.load(p)
            self.assertEqual(loaded["panel"]["max_rounds"], 5)
            self.assertEqual(loaded["panel"]["reviewers"], cfg.DEFAULTS["reviewers"])  # 未写项回落默认
            self.assertEqual(loaded["reviewers"][0]["name"], "echo")

    def test_set_value(self):
        import tempfile
        from polyreview import config as cfg
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.toml")
            cfg.write_template(p)
            cfg.set_value("max_rounds", "5", p)            # 裸键形式
            cfg.set_value("panel.reviewers", "kimi,codex,claude", p)
            loaded = cfg.load(p)
            self.assertEqual(loaded["panel"]["max_rounds"], 5)
            self.assertEqual(loaded["panel"]["reviewers"], ["kimi", "codex", "claude"])

    def test_batch_uses_custom_reviewer(self):
        # batch 路径也能用 config 里的自定义评审员（此前只支持 MCP 路径）
        import tempfile
        from polyreview.adapter import Adapter
        from polyreview import config as cfg
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.toml")
            open(p, "w").write(
                '[[reviewer]]\nname = "echo"\nnew_cmd = ["echo", "hello-{prompt}"]\n')
            loaded = cfg.load(p)
            item = dict(loaded["reviewers"][0]); item.setdefault("binary", "echo")
            a = Adapter(**item)
            out, err, rc = a.run("WORLD", None, None)
            self.assertEqual(out, "hello-WORLD")


class TestInit(unittest.TestCase):
    def test_skill_install(self):
        import tempfile
        from polyreview.cli import _install_skill
        with tempfile.TemporaryDirectory() as d:
            import polyreview.cli as cli
            old = cli._SKILL_DIRS["claude"]
            cli._SKILL_DIRS["claude"] = d
            try:
                dst = _install_skill("claude")
                self.assertTrue(os.path.isfile(os.path.join(dst, "SKILL.md")))
            finally:
                cli._SKILL_DIRS["claude"] = old


class TestAddReviewer(unittest.TestCase):
    def test_add_and_roundtrip(self):
        import tempfile
        from polyreview import config as cfg
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.toml")
            cfg.write_template(p)
            cfg.add_reviewer("aider", "aider --message {prompt} --yes-always",
                             resume_cmd="aider --resume {session} --message {prompt}",
                             session_regex=r"session (\S+)", path=p)
            loaded = cfg.load(p)
            r = [x for x in loaded["reviewers"] if x["name"] == "aider"][0]
            self.assertEqual(r["new_cmd"][0], "aider")
            self.assertIn("{session}", r["resume_cmd"][2])


class TestInitHostPick(unittest.TestCase):
    def test_invalid_host_shows_menu(self):
        import subprocess as sp
        r = sp.run([sys.executable, "-m", "polyreview", "init", "--host", "windsurf"],
                   capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("qoder", r.stdout + r.stderr)      # 教学表出现
        self.assertIn("polyreview init", (r.stdout + r.stderr))


class TestNewAdapters(unittest.TestCase):
    def test_gemini_qwen_session_from_json(self):
        out = '{"session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "text": "ok"}'
        for name in ("gemini", "qwen"):
            a = REGISTRY[name]
            self.assertEqual(a.extract_session(out, ""), "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
            self.assertIn("--output-format", " ".join(a.new_cmd))  # 无 json 提不到 session id

    def test_aider_stateless(self):
        a = REGISTRY["aider"]
        self.assertIsNone(a.resume_cmd)   # 无续聊: 会话 id 不在 stdout, 每次新会话
        self.assertIn("--message", a.new_cmd)

    def test_registry_count(self):
        self.assertEqual(len(REGISTRY), 9)
