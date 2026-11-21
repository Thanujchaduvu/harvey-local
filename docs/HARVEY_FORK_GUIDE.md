# Merging into your fork of Harvey

The assignment requires a **fork** of `https://github.com/ethanplusai/harvey`. This package is self-contained so you can extend the fork without depending on Claude. What I found when inspecting the repository (current `main`):

* The Python package is now named `sellbird/` (legacy `harvey/` shim). About 28k lines, **AGPL-3.0**.
* Its LLM layer, `sellbird/brain.py`, drives the **Claude Code CLI** or **Codex CLI** (subscription-based), and `integrations/quota.py` calls `api.anthropic.com` for usage. These are exactly the paid dependencies the assignment forbids.
* `Brain.__init__` has a public seam: `Brain(state, brain_config, transport=...)` where `transport` is `async (prompt, *, agent, task, timeout, expect_json) -> str`. `app.llm_client.transport` has that signature and returns `""` on failure.

I ran `scripts/audit_no_cloud.py` on the fork: **78 findings in 12 files**: `codex.py` (24), `mcp_install.py` (22), `claude_runtime.py` (11), `brain.py` (5), `config.py` (4), `setup.py` (3), `state.py` (2), `integrations/quota.py` (2), `cli.py` (2), `usage.py`, `web/index.html`, `.github/workflows/tests.yml`. I have not modified the fork. The steps below are a plan, not a verified patch.

## Plan
1. **Fork and clone.** Create `harvey_local/` inside the fork and copy this repo's `app/`, `frontend/`, `data/`, `scripts/`, `tests/`, `docs/` into it (or keep it as a sibling package).
2. **Swap the brain.** In `sellbird/main.py` (and `cli.py`) construct `Brain(state, cfg.brain, transport=harvey_local.llm_client.transport)`. Check that `preflight()`, `is_within_budget()` and the usage/quota calls are skipped when a transport is given; patch them to return "OK / within budget" for the local transport.
3. **Delete the paid paths.** Remove `codex.py`, `claude_runtime.py`, `integrations/quota.py`, `mcp_install.py` (installs MCP into Claude/Codex), the Claude/Codex branches of `brain.py`/`setup.py`/`state.py`/`usage.py`, the `fake_anthropic.py`/`fake_codex.py` tests and the Codex CI variables. Change `BrainConfig.provider` default to `ollama` and drop `claude|codex` from `sellbird.yaml` and docs.
4. **Prove it.** `python scripts/audit_no_cloud.py /path/to/fork` must report 0 findings. Keep the report as evidence.
5. **Reuse Harvey's strengths where they help**, e.g. its skill/prompt files and Scout/Writer structure, but note that reused AGPL code makes the combination AGPL. Replace anything that shells out to `claude`/`codex` or requires a Claude subscription.
6. **Add the assignment features** from this package: hardware detection, queue, network guard, multi-product ICP, scoring, reply classification and the Trace page.
7. **Keep one README** that states what is from upstream Harvey and what you added.

If time is short, a defensible submission is: fork -> add this package under `harvey_local/` -> make it the documented entry point -> run the audit against only the code you ship, and clearly document that legacy upstream modules are removed or unused. Do not ship legacy code paths that can still call Claude or Codex; the evaluators treat that as a failure condition.
