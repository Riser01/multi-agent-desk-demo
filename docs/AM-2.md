# Phase AM-2 Spec: Handoff Caps & Plan Validation (`safety.py`)

Build `safety.py` (pure Python stdlib + `desk`). `two_agent.py` automatically imports it once created. About 30 minutes
including the Your turn exercise.

**What you learn:** a planted note can steer a planner. Two plain-code barriers stop it: cut what the planner reads
(first barrier), then refuse a plan that does something the user never asked for (second barrier).

## Before you build: watch the attack (unguarded)
In `python app.py --setup two`, type `/drill`, then `Tidy up my tasks.`. The planner obeys the note and plans
`delete_task` for task 1 (Pay rent). The gate asks `[y/N]`:
- **Answer `n`.** Status `done-with-denials`, Pay rent stays. The human gate saved you this time.
- Optional, to see what an unguarded delete looks like: type `/reset`, `/drill`, `Tidy up my tasks.` again and answer
  `y` once. Pay rent disappears from `todo-list.md`. A tired human who types `y` is exactly what AM-2 protects against.
- Type `/reset` before you continue.

## Contract (main, `python check.py 2`)
1. Constants: `MAX_CONTEXT_CHARS = 600` (mitigates context flooding and trailing injection payloads) and `MAX_PLAN_STEPS = 5`.
2. `cap_context(text: str, max_chars: int = MAX_CONTEXT_CHARS) -> tuple[str, bool]`:
   - If `len(text) <= max_chars`, return `(text, False)`.
   - Otherwise return `(text[:max_chars] + " [truncated]", True)`.
3. `validate_plan(steps: list[dict], goal: str) -> list[str]`:
   - Return a list of plain-English reasons to refuse the plan (empty list `[]` means allowed).
   - Refuse if `len(steps) > MAX_PLAN_STEPS`.
   - Refuse any step whose `tool` is not in `desk.ALL_TOOLS`.
   - Refuse any irreversible tool (`delete_task`, `cancel_event`) if none of `desk.DELETE_WORDS` appear in `goal.lower()`.

Verify with: `python check.py 2` -> `AM-2 ...: all 5 green`.

## Your turn (8 min, `python check.py 2 your-turn`)
Add one more rule to `validate_plan`: refuse any step that repeats an earlier identical step (same `tool` and same
`args`), naming the step number in plain English (e.g. `step 2 repeats an earlier identical step (list_tasks)`).
The same tool with different args (add A, add B) is still allowed.
- Coding agent prompt: `In safety.py validate_plan(), reject any plan where two steps have the same tool and args, and return a plain-English reason naming the step. Run python check.py 2 your-turn.`
- Watch-only: write the rule in one sentence, plus one plan that must fail and one that must pass.
- Expected: `AM-2  Your turn: duplicate-step rule (optional exercise): all 2 green`. `python check.py` also shows this
  line, but it never turns the main score red: it is optional.

## Re-test the attack (guarded)
`/drill`, then `Tidy up my tasks.`:
```text
WARN  [handoff] cap context cut to 600 chars
INFO  [planner] sees: goal + desk notes (612 chars, capped); tools: none
INFO  [planner] proposed 1 step(s): ['list_tasks']
status: done  |  calls: 1  |  answer: list_tasks: Tasks: ...
```
No gate question appears, because the cap removed the override before the planner read it. `validate_plan` is the
second barrier: if a planner were fooled anyway (an override early in a short note slips under 600 characters), the
plan is refused with `status: plan-rejected` and nothing runs.
