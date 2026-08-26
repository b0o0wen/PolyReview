# Roadmap

## Design decisions (why, not just what)

- **Host arbitration is the primary mode.** Your IDE agent (Qoder / Claude Code /
  Cursor…) drives the loop and drafts adopt/rebut dispositions; you approve.
  Human-in-the-loop arbitration is the differentiator vs. fully-automated review
  bots — it stays the core.
- **The CLI stays single-round (`polyreview review`) on purpose.** It exists for
  CI gating (exit code 0 = unanimous APPROVE) and scripting, not as a second
  interactive frontend. An interactive `run` command was considered and
  deliberately not pursued — see "Rejected" below.
- **Reviewer = agent, not model.** You pick which CLIs sit on the panel; each
  keeps its own model/config. Cross-vendor diversity is the whole point
  (`identity()` lets you verify it).
- **Stateful sessions are a bonus, never a dependency.** Every request carries
  full context; session resume just adds caching and reviewer memory, with
  automatic fallback.

## v0.1.x (current)

- [ ] GitHub public + push, PyPI `polyreview` release
- [ ] Demo GIF (host mode: cross-vendor reviewers converge in 3 rounds) + social preview card
- [ ] `uvx polyreview demo` in README first screen; install.sh (curl | sh)
- [ ] Homebrew tap
- [ ] Case study (anonymized real session data → docs/methodology.md)
- [ ] GitHub Actions running the zero-cost test suite

## v0.2 candidates

- [ ] Verify experimental adapters (gemini / qwen / aider / qoder) on real installs → promote out of experimental
- [ ] `polyreview transcript <slug>` — replay any review round from disk
- [ ] Same-model warning: alert when two panel members resolve to the same underlying model (cross-validation void)
- [ ] npm thin wrapper for `npx polyreview` (decide by uvx adoption data)

## Rejected (for now)

- **Interactive `polyreview run` (terminal arbitration loop).** Technically
  small, but it forks the narrative: PolyReview's arbiter is a host LLM
  supervised by a human, not a terminal prompt sequence. Revisit only if
  terminal-only users ask loudly.
- **`--auto-arbitrate` (third model decides adopt/rebut, runs to convergence).**
  No human braking on cost or judgment; turns us into the automated bot we're
  differentiating from. A community experiment could explore it behind an
  explicit opt-in, never as default.
