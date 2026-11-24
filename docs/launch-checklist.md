# Launch checklist: the Desk Assistant Team

Fill it in for your own agent before anyone else uses it. A "no" or a blank is a no-go until fixed.

## Ownership
- [ ] **Owner** named (one person, not a team): ______________________
- [ ] **On-call / rollback owner** named, and they know the rollback command: ______________________
- [ ] **Business case** in one sentence: what does it save or earn per task, and what does a task cost?

## Cost
- [ ] Cost per task measured on real runs (`compare.py --live --runs 5`): median $______, range $______ (date: ______, model: ______)
- [ ] **Cost ceiling** per run set (`--ceiling`): $______ and tested (status `cost-ceiling` seen)
- [ ] Per-run **call cap** set (`--max-calls`): ______
- [ ] Model routing written down (`prod.ROUTING`), cheapest model where judgement is not needed

## Safety
- [ ] Every irreversible tool asks a human with the real item named (gate)
- [ ] Each agent has only the tools it needs (allow-lists)
- [ ] Plan validation on (`validate_plan`) and the planted-note scenario S4 passes
- [ ] Reviewer on for irreversible actions, round cap 2
- [ ] Untrusted text (notes, pasted content) never reaches the supervisor or reviewer

## Release
- [ ] Every run carries a **version stamp** (app, prompt hash, model per role)
- [ ] **Canary**: new version to ______% of users first (`extras/canary.py --set N`)
- [ ] **Rollback** is one step and was rehearsed (`extras/canary.py --rollback`)

## Watching it
- [ ] Logs and reports kept (`logs/`, `out/`) and someone reads them
- [ ] **Sampled review**: ______% of runs read by a person each week (`extras/monitor.py --share`)
- [ ] **Alerts** that matter: cost spike, denial rate, stopped runs (`extras/monitor.py`)
- [ ] Every real failure becomes a **regression case** (`extras/monitor.py --to-regression`) and `compare.py` passes it

## Go / no-go
| Question | Answer |
|---|---|
| Does the team beat one agent on the numbers that matter (pass rate, safety), at a cost we accept? | |
| Is there a single owner who can roll it back today? | |
| **Decision** (go / no-go / go with canary at __%) | |
