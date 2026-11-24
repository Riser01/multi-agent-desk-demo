# Phase W7-7: cost meter, model routing and a version stamp (18 min, incl. Your turn)

## The concept
A team multiplies calls, so it multiplies the bill, and nobody sees a bill **per task** unless code adds it up.
- **Cost meter:** every call is priced as it happens: `tokens x list price`. `charge()` adds; `check()` is the rule.
- **Cost ceiling:** once a run's cost passes it, `check()` raises `CostCeilingReached` and the run stops with status `cost-ceiling`. A runaway loop costs at most the ceiling.
- **Model routing:** routing decisions and single tool calls go to the cheapest model; the planner and the reviewer, where judgement matters, get a stronger one.
- **Version stamp:** every run says which app version, which prompts (a hash) and which model per role. That is what you need the day a change makes things worse and you roll back.

Honest numbers: the free tier costs nothing, so every cost is **notional, at list price** on the date in `data/prices.json` (source URL inside). Offline, tokens are estimates, so offline costs only show the shape.

## What you build
`prod.py`: `APP_VERSION`, `PRICES_PATH`, `ROUTING`, `load_prices`, `price_usd`, `CostMeter`, `prompt_version`, `version_stamp`; and `production()` in `agent.py`.
Contract: `02-technical-spec.md` section 10.

## Ask your agent exactly this
> Read `AGENTS.md` and `docs/02-technical-spec.md`. Build Phase W7-7 only: `prod.py` exactly as section 10 (prices from `data/prices.json`, `charge` never raises, `check` raises `llm.CostCeilingReached`), and in `agent.py` use the meter, `ROUTING` and `version_stamp` when `prod` imports (section 10, last bullet). Make `python check.py 7` pass, then `python check.py` and `python check.py style`. Never edit `tests/` or the provided files.

## Check
```bash
python check.py 7
python check.py
python check.py style
```
```text
Phase W7-7  Cost meter and version stamp: all 7 green
Style   comment standard: ok (9 files checked)
```

## Try it
```bash
python agent.py "Cancel the team sync on Wednesday and remind me to email Anil." --setup team --review --approve yes
```
What you should see (`sample-runs/07a-cost-and-version.txt`):
```text
INFO  ... [run       ] run     start team-review  mode=fake (...)  version=app=1.0.0 setup=team prompts=... langgraph=1.2.23 models=...
INFO  ... [supervisor] model   stand-in (priced as gemini-2.5-flash-lite) replied in 0.00s (140 in / 19 out tokens, est.): ...
INFO  ... [supervisor] cost    $0.000022 this call, $0.000022 so far (notional)
INFO  ... [reviewer  ] model   stand-in (priced as gemini-3.5-flash-lite) replied ...
status: done
```
`out/latest.html` now shows the version in the header and a cost tile "notional, at list price, 2026-11-24".

## Your turn: set a cost ceiling and see the run stop
```bash
python agent.py "Cancel the team sync on Wednesday and remind me to email Anil." --setup team --review --approve yes --ceiling 0.0001
```
```text
WARN  ... [run       ] cap     cost-ceiling: cost ceiling reached: $0.000123 is over $0.000100 (notional)
status: cost-ceiling
```
Notice **where** it stopped: after the reviewer approved, before the cancel ran. *If time:* change one word in `SUPERVISOR_PROMPT` and run again. The `prompts=` hash in the stamp changes. Change `ROUTING` so the supervisor uses the stronger model: the notional cost goes up.

**Which model a live call uses.** From W7-7 on, `ROUTING` decides per role, and `GEMINI_MODEL` in `.env` is only the default for roles without a routing entry. On a live `429`, change the model names in `ROUTING`.

## What you learn
- Cost per task, not per token; a ceiling turns a number into a rule.
- Routing is the cheapest cost control there is.
- If you cannot say which prompt and model produced a run, you cannot roll back.

## Common mistakes
- `charge()` raising: then the cost of the last call is never logged.
- Pricing an unknown model as free (use the fallback).
- Comparing setups' costs without noticing routing: in `compare.py` the team is cheaper partly because its roles use the cheaper model, not only because its prompts are smaller.
