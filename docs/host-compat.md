# Host compatibility field notes

各 MCP host 的实测差异与 PolyReview 的应对。给贡献者排障用，都是真金白银踩出来的。

## 1. stdin 继承导致 CLI 挂起（最隐蔽）

MCP stdio server 的 stdin 是协议管道（host 持续持有）。子进程若继承它，
部分 CLI（实测 codex exec）检测到 stdin 可读会**等待输入，永久挂起**（实测卡 15 分钟无输出）。

**应对**：所有子进程 `stdin=subprocess.DEVNULL`（adapter.py 铁律 1）。
裸终端跑不触发（stdin 是 tty 或 null），只在 MCP 内触发——极易漏测。

## 2. structuredContent 不透传

codex 原生 `codex mcp-server` 把 threadId 放在 structuredContent 与事件流通知里。
部分 host（实测 Qoder）不把这些透传给会话 agent → 主持人拿不到 threadId →
永远无法续聊（实测 4 轮评审全部退化为新线程重发）。

**应对**：不用原生 server，adapter 走 `codex exec` 子进程，session id 从 stderr
头部解析后**放进返回的明文 JSON**。这也是 PolyReview 自己做 wrapper 而不直接
挂原生 mcp-server 的原因。

## 3. MCP roots 支持不一

标准 MCP roots 允许 server 向 host 询问当前工作区。实测 Qoder 不提供，
Claude Code 系 host 提供。

**应对**：cwd 解析链 = 显式 `cwd` 参数 → roots → `POLYREVIEW_CWD` env →
进程 cwd（带 .git 等工程标记）→ 未设置。skill 层规则：host 驱动时**显式传 cwd**，
不赌 roots。

## 4. 会话提示行位置因 CLI 而异

- kimi：stdout 是干净回复，`To resume this session: kimi -r <id>` 在 **stderr**
- codex：stdout 干净，`session id: <uuid>` 在 **stderr 头部**
- claude：`--output-format json` 时 session_id 在 **stdout JSON 字段**

**应对**：`extract_session` 同时搜 stderr+stdout（adapter 铁律 2）。

## 5. host 环境变量污染

某些 host 会给会话进程注入 env（实测 Qoder 注入 `ANTHROPIC_BASE_URL` →
claude CLI 被路由到非 Anthropic 端点，"claude 评审员"实际是另一家模型）。

**应对**：评审员 = agent，但 `identity()` 必须能自检实际模型；交叉评审的前提
是评审团成员来自不同厂商，若两个评审员解析到同一模型应告警（roadmap）。
