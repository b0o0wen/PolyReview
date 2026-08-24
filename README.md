# Tribunal ⚖️

**Let your AI coding agents review each other.** Turn any combination of CLI agents — Codex, Claude Code, Kimi, Qoder, Trae, OpenCode — into a cross-review panel that interrogates your specs and diffs until they converge.

> One model reviewing itself is circular. Two *different vendors* cross-examining your design doc is a tribunal.

<!-- TODO(P2): GIF demo here — two vendors independently catching the same issue, verdict JSON, 3-round convergence timeline -->

## Why

- **Cross-vendor validation**: two reviewers from different model families independently locate the same defects far more often than chance — real sessions showed duplicate hits on 3 separate rounds ([methodology](docs/methodology.md))
- **Converging, not endless**: verdict protocol (`APPROVE`/`REVISE` + severity-tagged issues) with a host arbitrator — real sessions converge in 2-4 rounds
- **Stateful when it helps**: each reviewer resumes its own session across rounds (remembers what it flagged), with automatic new-session fallback — correctness never depends on the memory
- **Reviewer = agent, not model**: you pick which CLIs sit on the panel; each keeps its own model/config. `tribunal doctor` detects what's installed

## 30-second start (zero API cost)

```bash
pip install -e .   # or: uvx --from . tribunal demo
tribunal demo      # mock panel: REVISE → disposition → APPROVE, no keys needed
```

## Real usage

```bash
tribunal doctor                      # which reviewer CLIs are installed?
tribunal init --host claude          # prints `claude mcp add ...` for each reviewer
tribunal init --host qoder --write .vscode/mcp.json --reviewers kimi,codex

# batch: one round of cross-review on a spec (or an exported git diff)
tribunal review --artifact docs/design.md --reviewers kimi,codex --mode spec
git diff main...HEAD > review_state/pr/change.diff
tribunal review --artifact review_state/pr/change.diff --mode code
```

Or drive it from your MCP host (Qoder / Claude Code / Cursor / VS Code): each reviewer is a standard MCP server exposing `review(request, session_id, cwd)`, `identity()`, `whereami()`. The bundled [skill](skills/tribunal-review/SKILL.md) turns it into "multi-model cross-review" on demand.

## Supported reviewers

| Agent | Status | Resume |
|-------|--------|--------|
| kimi (Kimi Code) | tested | ✅ `kimi -r` |
| codex (Codex CLI) | tested | ✅ `exec resume` |
| claude (Claude Code) | tested | ✅ `--resume` |
| qoder | experimental | — |
| trae | experimental | — |
| opencode | experimental | — |

Add any other CLI via `reviewers.toml` (command templates + a session-id regex) — see [registry docs](tribunal/registry.py). PRs welcome for the experimental three; each verified adapter ships with its community's blessing.

## How it works

```
        ┌─ reviewer-kimi ──┐   verdict JSON
author ─┤                  ├─► host arbitrator ── adopt / rebut ──► next round
        └─ reviewer-codex ─┘   (blocker/major block; minor don't)      │
                                                                      ▼
                                              unanimous APPROVE / max rounds
```

Full protocol & field notes: [docs/methodology.md](docs/methodology.md) · host quirks (MCP roots, stdin inheritance, structuredContent) in [docs/host-compat.md](docs/host-compat.md).

## Status

Alpha. Proven in daily use on two hosts (Qoder, Claude Code) with kimi+codex; experimental adapters pending community verification. MIT.

中文介绍：[README.zh-CN.md](README.zh-CN.md)
