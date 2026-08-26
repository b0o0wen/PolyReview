"""评审引擎：verdict 协议 + 多轮循环 + 落盘（batch CLI 路径）。

与 server.py（MCP 路径）共用 verdict 协议；host 内由 LLM 主持人驱动时走 MCP 工具。

统一"工件"（artifact）抽象：方案 md 与代码 diff 都是文件——
  方案模式: artifact = 方案文件路径
  代码模式: artifact = git diff 导出文件路径（host 侧先导出）
"""

import concurrent.futures
import json
import os
import re

VERDICT_SCHEMA = """{"verdict": "APPROVE 或 REVISE",
 "issues": [{"id": 1, "severity": "blocker|major|minor",
             "point": "问题描述，引用方案位置或代码 文件:行号", "suggestion": "可执行的修改建议"}],
 "summary": "100 字以内总评"}"""

_DIMS_SPEC = "架构合理性、技术风险与失败模式、成本与复杂度、可维护性、安全性"
_DIMS_CODE = "正确性与边界条件、错误处理与失败模式、并发与资源泄漏、性能、安全（注入/越权）、可测性、与周边代码一致性"

_PASS_RULE = ("通过标准：只有 blocker 和 major 问题才能让你给出 REVISE；minor 列出但不阻塞。"
              "没有 blocker/major 时必须给 APPROVE。")
_OUTPUT_RULE = ("输出要求：先不超过 200 字总评，然后必须以一个 ```json 代码块结尾，"
                "严格符合：" + VERDICT_SCHEMA)


def first_prompt(reviewer: str, artifact_path: str, mode: str = "spec", summary: str = "") -> str:
    role = "架构评审员" if mode == "spec" else "代码评审员"
    dims = _DIMS_SPEC if mode == "spec" else _DIMS_CODE
    return f"""你是资深{role} {reviewer}。请先完整读取评审对象后独立评审：
{artifact_path}
（对象概述：{summary or ('技术方案' if mode == 'spec' else '代码变更 diff')}）
请结合当前工作区整个仓库核实，耗时长属正常，充分核实后再下结论。

评审维度：{dims}。每个问题只提一次，聚焦最重要的 3-5 个问题，不要凑数。
{_PASS_RULE}
{_OUTPUT_RULE}"""


def re_review_prompt(reviewer: str, artifact_path: str, review_log: str) -> str:
    return f"""你是资深评审员 {reviewer}。这是复核轮（你此前提过意见）。
请先读取最新评审对象：{artifact_path}
可结合仓库代码核实处置是否落实。

你的职责：
1. 核对每条意见是否已合理处置（采纳是否到位、反驳是否成立）；
2. 只针对「处置不当」或「改动引入的新问题」提新意见，不要重复已解决的意见；
3. {_PASS_RULE}
{_OUTPUT_RULE}

===== 历轮评审记录（含作者处置）=====
{review_log}
===== 评审记录结束 ====="""


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_verdict(text: str) -> dict:
    """从回复提取 verdict。取最后一个合法 json 块；失败降级为 REVISE（parse_ok=False）。"""
    for raw in reversed(_JSON_BLOCK.findall(text or "")):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "verdict" in data:
            data["verdict"] = "APPROVE" if str(data["verdict"]).upper() == "APPROVE" else "REVISE"
            data.setdefault("issues", [])
            data.setdefault("summary", "")
            data["parse_ok"] = True
            return data
    return {"verdict": "REVISE", "issues": [], "summary": (text or "")[:200], "parse_ok": False}


def blocking_issues(verdict: dict) -> list:
    return [i for i in verdict.get("issues", [])
            if str(i.get("severity", "")).lower() in ("blocker", "major")]


def run_round(adapters: dict, artifact_path: str, round_dir: str, *,
              mode: str = "spec", summary: str = "", prior_sessions: dict | None = None,
              review_log: str = "", cwd: str | None = None) -> tuple[dict, dict]:
    """并行送审所有评审员。返回 (verdicts, sessions) 并落盘 round_dir。"""
    os.makedirs(round_dir, exist_ok=True)
    prior_sessions = prior_sessions or {}
    prompts, results, sessions = {}, {}, {}
    for name in adapters:
        if review_log:
            prompts[name] = re_review_prompt(name, artifact_path, review_log)
        else:
            prompts[name] = first_prompt(name, artifact_path, mode, summary)

    def call(name):
        return adapters[name].review(prompts[name], prior_sessions.get(name), cwd)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(adapters)) as pool:
        futs = {pool.submit(call, n): n for n in adapters}
        for fut in concurrent.futures.as_completed(futs):
            name = futs[fut]
            out = fut.result()
            sessions[name] = {"session_id": out["session_id"], "resumed": out["resumed"]}
            open(os.path.join(round_dir, f"{name}.raw.md"), "w", encoding="utf-8").write(out["reply"])
            if out.get("stderr"):
                open(os.path.join(round_dir, f"{name}.stderr.log"), "w", encoding="utf-8").write(out["stderr"])
            results[name] = parse_verdict(out["reply"])
            print(f"[{name}] {'续聊✓' if out['resumed'] else '新会话'} → {results[name]['verdict']}")

    json.dump(results, open(os.path.join(round_dir, "verdicts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(sessions, open(os.path.join(round_dir, "sessions.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return results, sessions


def all_approve(verdicts: dict) -> bool:
    return all(v["verdict"] == "APPROVE" for v in verdicts.values())


def demo() -> int:
    """零成本演示：两个 mock 评审员，2 轮收敛（REVISE → 处置 → APPROVE）。"""
    from .mock import MockAdapter
    adapters = {n: MockAdapter(n) for n in ("mock-alpha", "mock-beta")}
    artifact = "/dev/null/spec-or-diff.md"  # mock 不读文件，仅占位
    state = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "demo_state")

    print("── PolyReview demo（mock，零 API 成本）──")
    v1, s1 = run_round(adapters, artifact, os.path.join(state, "round_1"))
    print(f"round 1: {'全票 APPROVE' if all_approve(v1) else 'REVISE（处置后复核）'}")

    if not all_approve(v1):
        log = "意见#1 已采纳：补充了失败模式章节（演示用假处置）。"
        v2, s2 = run_round(adapters, artifact, os.path.join(state, "round_2"),
                           review_log=log, prior_sessions={
                               n: info["session_id"] for n, info in s1.items()})
        print(f"round 2: {'全票 APPROVE ✅ 收敛' if all_approve(v2) else '仍未收敛'}")
        return 0 if all_approve(v2) else 1
    return 0
