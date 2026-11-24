# Where to look (one page)

| You want to... | Look at |
|---|---|
| start from zero | `GUIDE.md` (install, key, first prompt, every phase) |
| know the rules your coding agent follows | `AGENTS.md` |
| see the whole day on one page | `docs/00-overview.md` |
| know the exact names, state keys and message formats | `docs/02-technical-spec.md` |
| do one phase | `docs/phase-W7-N.md` (concept, prompt, check, try-it, expected output, common mistakes) |
| see what a run should print, without running it | `docs/sample-runs/` (recorded offline, labelled; `.html` report pages for the main runs) |
| catch up after falling behind | the join-here blocks in `GUIDE.md`, `checkpoints/` |
| run the day (instructor) | `docs/instructor-runbook.md` |
| try the drills | `docs/drills.md` |
| read one run as a page | `out/latest.html` (any browser) |
| read one run as text | `logs/latest.log`; as data: `logs/latest.jsonl` |
| see what an agent actually received | the `saw` lines in the terminal, "what it saw" rows in the HTML |
| find out why a check fails | the `requirement:` line from `python check.py N`, then the spec section it names |
| compare with a finished version | `solution/` (after two tries, or after green) |
| compare one agent vs a team | `python compare.py`, then `out/compare.html` |
| decide whether to launch | `docs/launch-checklist.md` |
| go further | `extras/fanout.py` (parallel), `extras/canary.py` (rollout), `extras/monitor.py` (review, alerts, regression cases) |
| understand how this maps to last week | `docs/harness-map.md` |
| know what goes wrong at the edges | `docs/edge-cases.md` |
