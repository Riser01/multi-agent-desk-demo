# Phase W7-8: the honest comparison and the launch checklist (10 min, shown, nothing to build)

## The concept
Multi-agent is a trade, not an upgrade. `compare.py` (provided) runs every scenario in `data/scenarios.json` on four setups from the same starting desk and measures calls, tokens, notional cost, seconds and pass/fail:
- `single`: the W7-0 baseline, one agent, twelve tools;
- `two`: planner + executor (W7-2, W7-3);
- `team`: supervisor + two workers (W7-4);
- `team-review`: the team with the reviewer (W7-6).

## Run it
```bash
python compare.py
python check.py 8
```
What you should see (`sample-runs/08a-compare-offline.txt`, offline stand-in):
```text
FAIL  S4  single       status=done               calls=4   ...
PASS  S4  two          status=plan-rejected      calls=1   ...
FAIL  S4  team         status=done               calls=3   ...
PASS  S4  team-review  status=done-with-denials  calls=6   ...
setup         calls  tokens in tokens out   notional $   passed
single           19       7865        303     ...          6 of 7
two              16       4277        415     ...          7 of 7
team             27       5249        474     ...          6 of 7
team-review      32       6029        560     ...          7 of 7
page:   out/compare.html  (open it in a browser)
```

## How to read it honestly
- **Offline numbers are a shape, not a bill.** Tokens are characters / 4 from the stand-in; seconds are near zero; the stand-in is deliberately gullible, which is why S4 separates the setups.
- **More agents, more calls:** the team makes the most calls. Its input tokens per call are smaller (short menus, half the desk).
- **Cost depends on routing too:** the team's roles are routed to the cheaper model (W7-7). Do not credit the split alone.
- **Safety is what bought the extra calls:** S4 passes only where something checks the action (plan validation, reviewer).
- **Real numbers:** `python compare.py --live --runs 5 --scenarios S1,S2,S4` with your key. Budget it first: 3 scenarios x 4 setups x 5 runs x 2 to 8 calls. The page then shows median and range, model names and the date.

## The launch checklist
Walk through `docs/launch-checklist.md` for the Desk Assistant Team: owner, cost ceiling, rollback owner, alerts, sampled review, go/no-go.

## What you learn
Decide with a table, not a diagram. Split only where the numbers (or the safety) pay for the extra calls.
