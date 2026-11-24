# Guide: build the Desk Assistant Team, phase by phase

Do the steps in order. Copy each command into a terminal, one block at a time. Run the check after every phase. Morning (Build Hour 1): W7-0 to W7-3. Afternoon (Build Hour 2): W7-4, W7-6, W7-7, then W7-8 is shown. Finishing W7-0 to W7-3 is a complete outcome.

Every command below runs **offline** with the stand-in model (no key, no quota). Expected outputs are pasted from real recorded offline runs in `docs/sample-runs/`; times, token counts and file names will differ a little on your machine. Look for the key lines, not identical text.

> **Can't or don't want to code?** You can follow the whole day without building anything. Use `docs/predict-sheet.md`: before each run, write what you expect; then open the recorded run in `docs/sample-runs/` (the `.txt` files are the terminal output; the `.html` files are the report pages, open them in a browser). That is a complete way through the day.

## Words used here (one line each)
- **Terminal:** a window where you type commands (Mac: Terminal app; Windows: Command Prompt, called `cmd`).
- **venv:** a private Python environment for this project only, so installs do not touch the rest of your computer.
- **pip:** Python's installer; `pip install -r requirements.txt` installs what this project needs.
- **Coding agent:** an AI assistant that edits files and runs commands in this folder for you.
- **Langfuse:** an optional website that draws each run as a tree. You can skip it.

## Minutes for the day
| Build Hour 1 (morning) | Minutes | | Build Hour 2 (afternoon) | Minutes |
|---|---|---|---|---|
| W7-0 baseline (run only) | 5 | | W7-4 supervisor + workers | 22 |
| W7-1 state + one agent node | 22 | | W7-6 reviewer | 20 |
| W7-2 planner + executor | 25 | | W7-7 cost meter + ceiling (Your turn) | 18 |
| W7-3 caps + validation (incl. Your turn 8) | 18 | | W7-8 comparison (shown) + monitor/canary demo | 10 |
| **buffer** | **15** | | **buffer** | **15** |

Items marked *if time* can be skipped without breaking anything later.

---

## Setup (do this before Sunday)

### Step 1. Install git (or skip it and use the ZIP)
- **Mac:** open Terminal and run `git --version`. If a pop-up offers "command line developer tools", click Install and wait (several minutes).
- **Windows:** download from https://git-scm.com/downloads, run the installer with the defaults, then open a **new** Command Prompt.

```bash
git --version
```
You should see `git version 2.x`. No git? Use Option A in Step 3.

### Step 2. Install Python 3.11 or newer
Download from https://www.python.org/downloads/ (Windows: tick **Add python.exe to PATH** on the first installer screen). Then open a **new** terminal and check:

Mac:
```bash
python3 --version
```
Windows:
```bash
py --version
```
You need 3.11 or higher. A new Mac often has 3.9: if it says 3.9 or lower, install from python.org, open a **new** terminal, and check again.

### Step 3. Get the project
Repo: https://github.com/Riser01/multi-agent-desk-demo (if the link shows 404, ask your instructor for the ZIP or the current link).

**Option A: ZIP.** Open the repo page, click the green **Code** button, then **Download ZIP**. Unzip it (Mac: double-click; Windows: right-click, **Extract All**). The folder is called `multi-agent-desk-demo-main`; on Windows it is often one folder **inside** another with the same name: open folders until you see `check.py`, `README.md` and `GUIDE.md` together. That is the project folder. Windows tip: if Documents is inside OneDrive, put the folder in `C:\work` instead (OneDrive can lock files while they sync).

**Option B: git.** Mac:
```bash
cd ~/Documents
```
Windows:
```bash
cd %USERPROFILE%\Documents
```
Then:
```bash
git clone https://github.com/Riser01/multi-agent-desk-demo.git
```
```bash
cd multi-agent-desk-demo
```

### Step 4. Open a terminal in the project folder
- **Mac:** Terminal, type `cd ` (with a space), drag the project folder into the window, press Return.
- **Windows:** open the project folder in File Explorer, click the address bar, type `cmd`, press Enter. Use Command Prompt, not PowerShell (PowerShell twins are given where they differ).
- **In Cursor:** File > Open Folder, choose the project folder, then Terminal > New Terminal.

### Step 5. Make the venv and install
Mac:
```bash
python3 -m venv .venv
```
```bash
source .venv/bin/activate
```
Windows (Command Prompt):
```bash
py -m venv .venv
```
```bash
.venv\Scripts\activate
```
Windows PowerShell instead: run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then `.venv\Scripts\Activate.ps1`.

Then (both):
```bash
pip install -r requirements.txt
```
This installs LangGraph and `google-genai` (the Gemini library, only used by `--live` runs). You should see `(.venv)` at the start of the prompt. **In every new terminal, `cd` to the folder and run the activate line again.** From here on, every command is `python ...` (with the venv on, `python` is the right Python on Mac and Windows).

### Step 6. The first check
```bash
python check.py
```
What you should see (nothing built yet, and that is correct):
```text
Setup   provided files: all 24 green
Phase W7-1  State and one agent node: not built yet (state.py does not exist)
Phase W7-2  Planner and executor: not built yet (handoff.py does not exist)
...
Phase W7-8  The comparison (provided; runs your graphs): not built yet (graph.py does not exist)
Style   comment standard: ok (0 files checked)
```

### Step 7. A coding agent: Cursor
We recommend **Cursor** (an editor with a built-in coding agent and terminal): download from https://cursor.com/download, install, sign in. Check its pricing page for the current plan limits: a free plan may run out during a full day of building, so test it before Sunday. (Already use another coding agent that can edit files and run commands, such as Claude Code? That works the same way. A chat in a browser tab will not.)

1. In Cursor: File > Open Folder, choose the project folder (the one with `check.py`).
2. Open the agent panel (the chat on the right), choose **Agent** mode, and allow it to edit files and run terminal commands.
3. Your first message, exactly:
```text
Read AGENTS.md first and follow it for this whole session. Use "python" (not python3) for every command, with the .venv turned on. Never open or print my .env file. Do not use --live. Reply "ready" when you have read it.
```

### Step 8 (optional). A free Gemini key, for live runs only
You do not need it to build or to pass any check. It lets you see what a real model does (`--live`).
1. https://aistudio.google.com/apikey, sign in with a personal Google account, **Create API key**, copy it.
2. Make `.env` (a file whose name starts with a dot is hidden in Finder; on Windows make sure it does not become `.env.txt`):

Mac:
```bash
cp .env.example .env
```
```bash
open -e .env
```
Windows:
```bash
copy .env.example .env
```
```bash
notepad .env
```
3. Paste after `GEMINI_API_KEY=` with no spaces or quotes. Save (Windows: if Notepad shows a Save As box, set "Save as type" to "All files" so it stays `.env`, not `.env.txt`). Never paste the key into the agent chat.

### Step 9 (optional). Langfuse
Free account at https://cloud.langfuse.com, a project, API keys into the three `LANGFUSE_` lines of `.env`, then:
```bash
pip install "langfuse==5.2.0"
```
Prompts and task text go to Langfuse: toy data only. Without it, `--export console` shows the same tree in your terminal.

### Open your results (after any run)
Mac:
```bash
open out/latest.html
```
```bash
open -e logs/latest.log
```
Windows:
```bash
start out\latest.html
```
```bash
notepad logs\latest.log
```
Log lines are long: make the terminal window wider, or add `--quiet` to a command to see only the summary.

---

## How every phase works
1. Open `docs/phase-W7-N.md`. Copy the block under **Ask your agent exactly this** into your coding agent (or the short prompt below).
2. Approve its edits.
3. Run the two checks: `python check.py N` (this phase must be green) and `python check.py` (earlier phases still green; later ones say "not built yet").
4. Run the try-it commands and compare with **What you should see**. Open `out/latest.html`.

**`agent.py` is provided.** It is the command you run in every phase; it uses the files you build. Before W7-1 is built it answers `configuration error: graph.py is not built yet (W7-1)`.

**How approval works here:** when an irreversible action needs a yes, the gate asks in the terminal and waits (a plain blocking question, `APPROVAL NEEDED: ...`). This is **not** LangGraph's `interrupt()`: there is no pause-and-resume and no checkpointer. `interrupt()` is shown on the slides as the production way to pause for a human.

### The stuck ladder
1. Copy only the line starting `Phase W7-N, requirement:` into your agent and say **"fix only this"**.
2. After **two** failed tries: paste the phase's section of `docs/02-technical-spec.md` into the agent.
3. Still stuck: ask the agent to compare with `solution/<file>.py` (allowed after two tries).
4. Behind the class: use a **join here** block below.
5. Never edit `tests/`. A green check is the grade.

---

## Build Hour 1 (morning): one agent, then two

### W7-0: why one agent breaks (5 min, nothing to build)
Purpose: measure the thing you are about to split. What you learn: one agent pays for twelve tools on every call; look-alike tools invite the wrong pick.

```bash
python baseline.py "Add a dentist appointment on Fri 27 Nov 10:00 and add a task to buy a gift for Anil." --approve no
```
What you should see:
```text
INFO  +  0.00s  [agent     ] model   stand-in replied in 0.00s (401 in / 22 out tokens, est.): {"tool": "add_event", ...}
INFO  +  0.00s  [agent     ] model   stand-in replied in 0.00s (431 in / 15 out tokens, est.): {"tool": "add_task", ...}
INFO  +  0.00s  [run       ] run     ended: status=done after 3 model calls, 1285 in / 79 out tokens (est.), 0.0s
status: done
```
A **replayed** failure shape (hand-written, labelled REPLAYED in every line):
```bash
python baseline.py "Archive the dentist task." --mode replay --replay data/replays/w7-0-misroute.json --approve no
```
```text
INFO  ... run     start baseline  mode=replay (REPLAYED (scripted): written by hand to show a known failure shape ...
WARN  ... [agent     ] gate    delete task 4: "Book dentist appointment"  ->  denied
status: done-with-denials
answer: Done: the dentist task is archived.
```
The answer is false: nothing was archived.

### W7-1: state and one agent node (22 min)
Purpose: the shared state every agent will use, and last week's agent as a graph. What you learn: reducers (merge vs overwrite), a loop as a conditional edge, caps and `recursion_limit`.

Short prompt:
```text
Read AGENTS.md and docs/phase-W7-1.md, then do exactly what "Ask your agent exactly this" says. Phase W7-1 only.
```
Check:
```bash
python check.py 1
```
```bash
python check.py
```
```text
Phase W7-1  State and one agent node: all 12 green
```
Try it:
```bash
python agent.py "Add File taxes, then show me my list." --setup single --approve no
```
```text
INFO  ... [agent     ] model   stand-in replied in 0.00s (388 in / 13 out tokens, est.): {"tool": "add_task", "args": {"text": "File taxes"}}
INFO  ... [agent     ] tool    add_task {"text": "File taxes"}  ->  ok: added task 9
INFO  ... [run       ] run     ended: status=done after 3 model calls, 1259 in / 45 out tokens (est.), 0.0s
status: done
report: out/latest.html  (open it in a browser)
```
Then type `n` at the question:
```bash
python agent.py "Delete the dentist task." --setup single --approve ask
```
```text
APPROVAL NEEDED: delete task 4: "Book dentist appointment". Cannot be undone. Allow? [y/N]
WARN  ... [agent     ] gate    delete task 4: "Book dentist appointment"  ->  denied
status: done-with-denials
```

**Join here (W7-1 not finished):** copy your own `state.py` and `graph.py` somewhere safe first (the zip overwrites them), then:
Mac:
```bash
unzip -o checkpoints/after-W7-1.zip
```
Windows (Command Prompt, Windows 10 or newer; it overwrites files):
```bash
tar -xf checkpoints\after-W7-1.zip
```
(Do not use Explorer's default Extract All: it makes a subfolder and the check still says "not built yet". If you use it, extract into the project folder itself and choose Replace.) Then:
```bash
python check.py
```
W7-1 should be green.

### W7-2: planner then executor, with a structured handoff (25 min)
Purpose: the first team of two. What you learn: the four parts of a handoff, least privilege per step, "a plan is a proposal, not a permission".

Short prompt:
```text
Read AGENTS.md and docs/phase-W7-2.md, then do exactly what "Ask your agent exactly this" says. Phase W7-2 only. If a function the phase asks for already exists (for example from a checkpoint), keep it and only create what is missing.
```
Check:
```bash
python check.py 2
```
```bash
python check.py
```
```text
Phase W7-2  Planner and executor: all 8 green
```
Try it:
```bash
python agent.py "Add File taxes, then show me my list." --setup two --approve no
```
```text
INFO  ... [planner   ] plan    2 step(s) | 1. add_task: Add File taxes  (why: the user asked for it) | 2. list_tasks: show me my list ...
INFO  ... [planner   ] handoff planner -> executor (step 1 of 2): Add File taxes
INFO  ... [executor  ] saw     task: Add File taxes | context: | tasks: | 1: Mon 23 Nov: renew car insurance | ...
INFO  ... [run       ] run     ended: status=done after 3 model calls, 740 in / 64 out tokens (est.), 0.0s
```
Same goal, roughly 1.5 to 2 times fewer input tokens than one agent with twelve tools (the exact numbers vary with wording). In `out/latest.html`, expand what the executor saw.

**Join here (W7-2 not finished):** copy your own `.py` files somewhere safe first, then:
Mac:
```bash
unzip -o checkpoints/after-W7-2.zip
```
Windows (Command Prompt, Windows 10 or newer; it overwrites files):
```bash
tar -xf checkpoints\after-W7-2.zip
```
(Do not use Explorer's default Extract All: it makes a subfolder and the check still says "not built yet". If you use it, extract into the project folder itself and choose Replace.) Then:
```bash
python check.py
```
W7-1 and W7-2 should be green; W7-3 says "not built yet".

### W7-3: break the handoff on purpose, then cap it (18 min, incl. Your turn 8)
Purpose: every arrow is an attack path. What you learn: refuse what changes meaning, cut what does not, check "did the user ask for this?" in code.

The instructor demos the three breaks first (planted note, huge note, a replayed bad plan); then you build the caps and `validate_plan`.

Short prompt:
```text
Read AGENTS.md and docs/phase-W7-3.md, then do exactly what "Ask your agent exactly this" says. Phase W7-3 only.
```
Check:
```bash
python check.py 3
```
```bash
python check.py
```
```text
Phase W7-3  Break the handoff and cap it: all 8 green
```
Try it (the planted note, with a human who clicks yes without reading):
```bash
python agent.py "Tidy up my list." --setup two --seed data/seeds/trap.json --approve yes
```
```text
WARN  ... [planner   ] plan    REJECTED: step 2 uses delete_task, which cannot be undone, but the goal never asks to delete, remove, clear or cancel anything; ...
status: plan-rejected
tasks left: 5
```
*If time:* the huge note and the replayed bad plan:
```bash
python agent.py "Show me my list." --setup two --seed data/seeds/long_note.json --approve no
```
```bash
python agent.py "Add File taxes and show me my list." --setup two --mode replay --replay data/replays/w7-3-bad-plan.json --approve no
```
(expected: a `cap` WARN line, then `status: done`; and `REJECTED: the plan has 7 steps; the cap is 5; ...`.)

**Your turn (8 min):** add one rule to `validate_plan`: **two identical steps in one plan are refused.** Prove it with a run and keep `python check.py` green. Other rule ideas are in `docs/phase-W7-3.md` (stretch).

---

## Build Hour 2 (afternoon): a team

**Join here (morning not finished):** copy your own `.py` files somewhere safe first, then:
Mac:
```bash
unzip -o checkpoints/after-W7-3.zip
```
Windows (Command Prompt, Windows 10 or newer; it overwrites files):
```bash
tar -xf checkpoints\after-W7-3.zip
```
(Do not use Explorer's default Extract All: it makes a subfolder and the check still says "not built yet". If you use it, extract into the project folder itself and choose Replace.) Then:
```bash
python check.py
```
W7-1 to W7-3 should be green. (The `solution/` folder ships with the repo; `AGENTS.md` tells your coding agent not to read it until you ask.)

**Important for this hour:** the team path (`--setup team`) has **no plan** to validate. Without `--review`, the gate and the human are the only defence against a planted note; W7-4's second try-it shows what that means, and W7-6 adds the reviewer.

### W7-4: supervisor and two specialist workers (22 min)
Purpose: dynamic routing and specialists. What you learn: `Command` handoffs, "what each agent sees" as a design, least privilege per worker.

Short prompt:
```text
Read AGENTS.md and docs/phase-W7-4.md, then do exactly what "Ask your agent exactly this" says. Phase W7-4 only. If a function the phase asks for already exists (for example from a checkpoint), keep it and only create what is missing.
```
Check:
```bash
python check.py 4
```
```bash
python check.py
```
```text
Phase W7-4  Supervisor and workers: all 7 green
```
Try it:
```bash
python agent.py "Add a dentist appointment on Fri 27 Nov 10:00 and add a task to buy a gift for Anil." --setup team --approve no
```
```text
INFO  ... [supervisor] route   -> calendar: Add a dentist appointment on Fri 27 Nov 10:00
INFO  ... [calendar  ] saw     task: Add a dentist appointment on Fri 27 Nov 10:00 | context: | events: | 7: Wed 25 Nov 15:00, Team sync | ...
INFO  ... [supervisor] route   -> tasks: add a task to buy a gift for Anil
INFO  ... [run       ] run     ended: status=done after 5 model calls, 964 in / 117 out tokens (est.), 0.01s
```
And the reason for the next phase (planted note, blind yes, no reviewer):
```bash
python agent.py "Tidy up my list." --setup team --seed data/seeds/trap.json --approve yes
```
```text
INFO  ... [tasks     ] gate    delete task 2: "Pay rent"  ->  approved
status: done
```
"Pay rent" is gone.

**Join here (W7-4 not finished):** copy your own `.py` files somewhere safe first, then:
Mac:
```bash
unzip -o checkpoints/after-W7-4.zip
```
Windows (Command Prompt, Windows 10 or newer; it overwrites files):
```bash
tar -xf checkpoints\after-W7-4.zip
```
(Do not use Explorer's default Extract All: it makes a subfolder and the check still says "not built yet". If you use it, extract into the project folder itself and choose Replace.) Then:
```bash
python check.py
```
W7-1 to W7-4 should be green.

### W7-6: a reviewer on risky actions (20 min)
Purpose: a second opinion before the human. What you learn: the critic pattern, a round counter as a conditional edge, defence in depth.

Short prompt:
```text
Read AGENTS.md and docs/phase-W7-6.md, then do exactly what "Ask your agent exactly this" says. Phase W7-6 only. If a function the phase asks for already exists (for example from a checkpoint), keep it and only create what is missing.
```
Check:
```bash
python check.py 6
```
```bash
python check.py
```
```text
Phase W7-6  Reviewer on risky actions: all 11 green
```
Try it:
```bash
python agent.py "Tidy up my list." --setup team --review --seed data/seeds/trap.json --approve yes
```
```text
WARN  ... [reviewer  ] review  rejected (round 1 of 2): delete task 2: "Pay rent" (the user's goal never asks to delete or cancel anything)
WARN  ... [reviewer  ] review  rejected (round 2 of 2): delete task 3: "Book dentist appointment" (...)
status: done-with-denials
tasks left: 5
```
*If time:*
```bash
python agent.py "Delete the dentist task." --setup team --review --approve no
```
(expected: the reviewer approves, the human gate still denies: `status: done-with-denials`.)

### W7-7: cost meter and ceiling (18 min, incl. Your turn)
Purpose: production basics. What you learn: cost per task, a ceiling as a rule, routing, versioning for rollback.

Short prompt:
```text
Read AGENTS.md and docs/phase-W7-7.md, then do exactly what "Ask your agent exactly this" says. Phase W7-7 only.
```
Check:
```bash
python check.py 7
```
```bash
python check.py
```
```bash
python check.py style
```
```text
Phase W7-7  Cost meter and version stamp: all 7 green
Style   comment standard: ok (9 files checked)
```
Try it:
```bash
python agent.py "Cancel the team sync on Wednesday and remind me to email Anil." --setup team --review --approve yes
```
```text
INFO  ... [run       ] run     start team-review  mode=fake (...)  version=app=1.0.0 setup=team-review prompts=... langgraph=1.2.23 ...
INFO  ... [supervisor] model   stand-in (priced as gemini-2.5-flash-lite) replied in 0.00s (140 in / 19 out tokens, est.): ...
INFO  ... [supervisor] cost    $0.000022 this call, $0.000022 so far (notional)
status: done
```
**Your turn:** set a ceiling and watch the run stop:
```bash
python agent.py "Cancel the team sync on Wednesday and remind me to email Anil." --setup team --review --approve yes --ceiling 0.0001
```
```text
WARN  ... [run       ] cap     cost-ceiling: cost ceiling reached: $0.000123 is over $0.000100 (notional)
status: cost-ceiling
```
*If time:* change one word in `SUPERVISOR_PROMPT` (the `prompts=` hash changes); route the supervisor to the stronger model in `ROUTING` (the cost goes up).

### W7-8: the honest comparison (10 min, shown)
```bash
python compare.py
```
```text
setup         calls  tokens in tokens out   notional $   passed
single           19       7865        303     0.003117   6 of 7
two              16       4277        415     0.001697   7 of 7
team             27       5249        474     0.000714   6 of 7
team-review      32       6029        560     0.001075   7 of 7
page:   out/compare.html  (open it in a browser)
```
Mac `open out/compare.html`, Windows `start out\compare.html`. Read `docs/phase-W7-8.md` for how to read this honestly (offline numbers are a shape; the team is cheaper partly because of routing), then walk `docs/launch-checklist.md`. The instructor also runs `extras/monitor.py` and `extras/canary.py` for five minutes.

---

## Live runs (optional, your quota)
Add `--live` to any `agent.py` or `baseline.py` command. Each run makes 2 to 8 model calls, capped at 30 (`--max-calls`). On a `429` the run waits and retries up to 70 seconds, then stops with a plain message. Which model is used: before W7-7, `GEMINI_MODEL` in `.env` (default `gemini-3.5-flash-lite`); from W7-7 on, `ROUTING` in your `prod.py` decides per role. To keep a live run, add `--record data/replays/my-run.json`; replay it later with `--mode replay --replay data/replays/my-run.json` (labelled REPLAYED (recorded)).

## If something goes wrong
| You see | Fix |
|---|---|
| `LangGraph is not installed` | turn the venv on (Step 5 activate line), then `pip install -r requirements.txt` |
| `'py' is not recognized` (Windows) | reinstall Python with **Add python.exe to PATH** ticked, open a new Command Prompt |
| `python3` opens the Microsoft Store (Windows) | use `py` before the venv and `python` after activating it |
| `running scripts is disabled` (PowerShell) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use Command Prompt |
| `.env` not found, or saved as `.env.txt` | redo Step 8; in Notepad's Save As box set "Save as type" to "All files"; on Mac press Cmd+Shift+. in Finder to see hidden files |
| `configuration error: graph.py is not built yet` | build W7-1 first (or use a join-here checkpoint) |
| `No API key` | only for `--live`: Step 8, or drop `--live` |
| `429` | quota: wait a minute; before W7-7 set another `GEMINI_MODEL`, from W7-7 change `ROUTING` in `prod.py` |
| `404` model not found | same as 429: another model name |
| `401` / `403` | the key is wrong: make a new one |

## Stretch (any time): `extras/`
```bash
python extras/fanout.py --parallel --delay 0.5
```
```bash
python extras/canary.py --set 20 --users 10
```
```bash
python extras/monitor.py
```
```bash
python check.py extras
```
See `docs/phase-W7-5.md`, `docs/drills.md` and the docstring at the top of each file.

## Quick reference
| Phase | Check | Expected |
|---|---|---|
| W7-1 | `python check.py 1` | all 12 green |
| W7-2 | `python check.py 2` | all 8 green |
| W7-3 | `python check.py 3` | all 8 green |
| W7-4 | `python check.py 4` | all 7 green |
| W7-6 | `python check.py 6` | all 11 green |
| W7-7 | `python check.py 7` | all 7 green |
| W7-8 | `python check.py 8` | all 2 green |
| All | `python check.py` | all green |
| Style | `python check.py style` | ok |
| Extras | `python check.py extras` | all 7 green |
