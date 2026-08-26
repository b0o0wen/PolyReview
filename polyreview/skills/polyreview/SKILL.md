---
name: polyreview
description: 多模型交叉评审（PolyReview）：并行调用配置的 MCP 评审员（任意数量，不同厂商 CLI agent，一家即与 host 形成交叉）对技术方案或代码变更做多轮交叉评审，默认有状态续聊（session_id 跨轮传递），主持人（当前会话 agent）对每条意见做采纳或反驳处置，循环直到全票 APPROVE 或达轮数上限（默认 20 轮）。仅当用户明确要求多模型交叉评审、交叉评审、交叉 review、cross review、cross-review、多人评审、多人 review（不限对象）、专家团评审、多人讨论、多 agent 评审，或点名任一 reviewer-*/评审团/polyreview 时使用；单人评审意图（"评审方案"、"review 一下"、"帮忙看看"）不要使用本 skill。
---

# PolyReview 多模型交叉评审（方案与代码）

## 触发条件

仅当用户明确要求多模型交叉评审、交叉评审、交叉 review、cross review、
cross-review、多人评审、多人 review（不限对象）、专家团评审、多人讨论、
多 agent 评审，或点名任一 reviewer-*/评审团/polyreview。
未指明对象时按上下文判定方案/代码模式，仍模糊则问一句。

## 评审模式

| | 方案模式 | 代码模式 |
|--|---------|---------|
| 工件 | 设计文档 .md | git diff 导出文件（`git diff <base>...HEAD > review_state/<slug>/round_N/change.diff`） |
| 处置 | 改方案出 vN+1 | 改代码后重新导出 diff |

## 工具调用（所有评审员统一）

`review(request="<请求全文>", session_id="", cwd="<当前工作区绝对路径>")`
→ 返回明文 JSON `{reply, session_id, resumed, cwd}`

- 工件**绝对路径**进 prompt，全文不内嵌（并行两调用 × 全文会超单条消息上限）
- 首轮 session_id 空；复核轮传上轮值续聊，resumed=false 自动降级
- cwd 必传（部分 host 不提供 roots，不传会读错代码库）
- 辅助工具：`identity()`（核对评审员实际模型）、`whereami()`（目录自检）

## 流程

```
- [ ] 1. 确定工件：方案路径 / 导出 diff；建 review_state/<slug>/round_N/
- [ ] 2. 并行送审全部评审员（config 里的 panel.reviewers，任意数量；可先逐个 identity 核对异构性）
- [ ] 3. 解析 verdict（最后一个 ```json 块）+ 提取 session_id → sessions.json
- [ ] 4. 全票 APPROVE → FINAL_REPORT.md 收尾
- [ ] 5. 否则逐条处置 blocker/major（采纳=改工件 / 反驳=写理由）→
       host_disposition.md → 复核轮续聊送审 → 回到 3
- [ ] 6. 超 max_rounds（默认 20）→ 分歧报告请用户裁决
```

## verdict 协议

```json
{"verdict": "APPROVE 或 REVISE",
 "issues": [{"id": 1, "severity": "blocker|major|minor",
             "point": "问题（方案位置或 文件:行号）", "suggestion": "可执行建议"}],
 "summary": "100 字内总评"}
```

只有 blocker/major 阻塞；minor 记录不阻塞。解析失败按 REVISE，下轮强制协议。

## 送审模板

### 首轮（spec 模式；code 模式把工件换成 diff 路径、维度换代码维度集）

```
你是资深评审员 {reviewer}。请先完整读取评审对象后独立评审：
{artifact_path}
（对象概述：{summary}）
请结合当前工作区整个仓库核实，耗时长属正常，充分核实后再下结论。
评审维度：{架构合理性、技术风险与失败模式、成本与复杂度、可维护性、安全性
 | 正确性与边界、错误处理、并发与资源泄漏、性能、安全、可测性、一致性}。
每个问题只提一次，聚焦最重要的 3-5 个问题。
通过标准：只有 blocker/major 才 REVISE；minor 不阻塞；没有则必须 APPROVE。
输出：先 ≤200 字总评，结尾必须一个 ```json 块（严格符合 verdict 协议）。
```

### 复核轮

```
你是资深评审员 {reviewer}。这是复核轮（你此前提过意见）。
请先读取最新工件：{artifact_path}；可结合仓库核实处置是否落实。
职责：1) 核对每条意见处置是否合理（采纳到位/反驳成立）；
2) 只针对处置不当或新引入问题提意见，不重复已解决项；
3) 通过标准与输出同首轮。
===== 历轮评审记录（含作者处置）=====
{review_log}
```

## 落盘（每轮 round_N/）

`reviewer-*.raw.md`（原始回复）/ `verdicts.json` / `sessions.json` /
`host_disposition.md` / `change.diff`（代码模式）。
全票后 `FINAL_REPORT.md`：轮次统计、采纳/反驳计数、遗留 minor、最终工件路径。

## 注意

- 超时默认 3600s（全仓评审耗时长属正常）；host 侧工具超时需 ≥ 此值
- MCP 工具不可见 → 提示 Reload；batch 兜底：
  `polyreview review --artifact <path> --reviewers kimi,codex [--mode code] [--round N]`
