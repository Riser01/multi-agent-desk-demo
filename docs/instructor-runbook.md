# Instructor Runbook — Sunday 29 Nov (v2)

Format: learners direct a coding agent with the phase prompts; you demonstrate the same prompts live. Nobody hand-types code.

## Pacing (2 x 120 min, >= 20 min Q&A each)
- **Build Hour 1 (10:30–12:30):** Opening + `single` warm-up (10) -> AM-1 `two_agent.py` (30) -> Q&A 1 (4) -> Break (5) -> AM-2 `safety.py` + `/drill` (18) -> Q&A 2 (3) -> Your turn duplicate-step rule (10) -> Re-test (5) -> Q&A 3 (3) -> Buffer (12) -> Wrap (5) -> Final Q&A (15). Total: 120 min (25 min Q&A).
- **Build Hour 2 (14:00–16:00):** Opening + `after-AM.zip` sync (5) -> PM-1a `team.py` Supervisor+Workers (20) -> Q&A 1 (3) -> Break (5) -> PM-1b `team.py` Reviewer + `/drill` (20) -> Q&A 2 (4) -> PM-2 `prod.py` + Your turn `/ceiling` + `/rollback` + `/monitor` + `/compare` (35) -> Q&A 3 (3) -> Buffer (7) -> Close (5) -> Final Q&A (13). Total: 120 min (23 min Q&A).

## Expected checks (solution, Python 3.11, langgraph 1.2.23, offline)
`python check.py` -> Setup 14, AM-1 5, AM-2 5, PM-1 9, PM-2 5 green, plus the optional `AM-2 Your turn ... all 2 green`
line. `python check.py stretch` -> 5 green. A fresh clone says "not built yet" for every phase: that is correct.

## Screen-share & Zoom tips
- **Zoom font size up** (18–20pt) and arrange terminal on the left, **`todo-list.md`** on the right so phone/Zoom learners see checkboxes and tasks update live.
- **Clear `logs/` before PM-2 Your turn** (`rm -rf logs` on Mac, `rmdir /s /q logs` on Windows cmd) so `/monitor` highlights the `cost-ceiling` run cleanly.
- AM-2 unguarded `/drill`: answer **`n`** at `[y/N]` first; then `/reset`, `/drill`, `Tidy up my tasks.` again and answer **`y` once** so the room sees Pay rent vanish from `todo-list.md`. `/reset` before building `safety.py`.

## Words to use (honesty rules)
- Approval `[y/N]` is a **blocking terminal callback**, not LangGraph `interrupt()` (the optional `docs/stretch.md` builds the real `interrupt()` gate).
- `sessions/` and `--resume` save your Desk and audit-only turn log **between turns** as JSON — not mid-turn graph checkpointing.
- Offline runs are labelled **`offline stand-in (not a real model)`** everywhere; token counts are **estimates** and costs are **notional, at list price read 2026-11-24** (gemini-3.5-flash-lite $0.30 in / $2.50 out, gemini-2.5-flash-lite $0.10 / $0.40 per 1M tokens). `/compare` is illustrative until run with `--live`.
- The two-agent setup makes **1 model call** (the planner); the executor only runs tools. The team makes **5** calls on the cancel + remind request, **6** with the reviewer, **7** on `/drill` with the reviewer.
- `/rollback` toggles a **track label** (and the stamped release); the prompt hash only changes when prompts, routing or the LangGraph version change. Real gradual rollout is on Saturday's slides.
- The optional `--export langfuse` is written against `langfuse==5.2.0` and tested offline with a fake recorder only; **not yet verified against a real Langfuse server as of 2026-11-25**. Without keys it prints the trace tree in the terminal (`--export console`), which is the safe live demo.

## Fast fallback when behind
- Morning behind: `unzip -o checkpoints/after-AM.zip` (Windows: `tar -xf checkpoints\after-AM.zip`) -> `two_agent.py` + `safety.py`.
- Afternoon behind after PM-1: `unzip -o checkpoints/after-PM1.zip` (Windows: `tar -xf checkpoints\after-PM1.zip`) -> adds `team.py`.
- PM-2 behind: copy `solution/prod.py` (Mac `cp solution/prod.py .`, Windows `copy solution\prod.py .`), run `python check.py`, and focus on the live `/drill`, `/ceiling`, `/rollback`, `/monitor`, and `/compare` demos.
