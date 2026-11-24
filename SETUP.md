# Setup: one page

Words used here: a **terminal** is a window where you type commands. **Green** means a check passed. The **project folder** is this folder (cloned or unzipped). The full walk-through from zero is in [`GUIDE.md`](GUIDE.md); this page is the short version.

## 1. Python 3.11 or newer
```bash
python3 --version
```
Windows: `py --version`. Before the venv exists use `python3` (Mac) or `py` (Windows); after activating it (step 2) use `python` everywhere, on both. Below 3.11? Install from https://www.python.org/downloads/ and open a new terminal.

## 2. A private environment, then the one package
Mac or Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Windows:
```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
You should see `(.venv)` at the start of the prompt. Run the activate line again in every new terminal. This installs LangGraph and `google-genai` (used only by `--live` runs). Windows: use Command Prompt; in PowerShell run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and activate with `.venv\Scripts\Activate.ps1`.

## 3. The first check
```bash
python check.py
```
Expected before you build anything: `Setup   provided files: all 24 green`, then every phase says **not built yet**. That is correct.

## 4. (Only for live runs) your free Gemini key
Everything works without a key. For `--live` runs:
1. https://aistudio.google.com/apikey, sign in, **Create API key**, copy it.
2. Mac/Linux: `cp .env.example .env` then `open -e .env`. Windows: `copy .env.example .env` then `notepad .env`.
3. Paste after `GEMINI_API_KEY=` (no spaces, no quotes). Save.

Paste the key **only** into `.env`: never into your coding agent's chat, never into a screenshot. `.env` is git-ignored.

## 5. (Optional) Langfuse
Free account at https://cloud.langfuse.com, a project, API keys into `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` in `.env`, then `pip install "langfuse==5.2.0"`. Prompts and task text are sent to Langfuse, so use toy data only. Skip it freely: `--export console` shows the same tree locally.

## If something goes wrong
| You see | Do this |
|---|---|
| `LangGraph is not installed` | turn on `(.venv)` and run `pip install -r requirements.txt` |
| `externally-managed-environment` from pip | you skipped the venv: do step 2 |
| `No API key` | only for `--live`: do step 4, or drop `--live` |
| `429` on a live run | free quota for that model: wait a minute; before W7-7 set `GEMINI_MODEL` in `.env`, from W7-7 change `ROUTING` in `prod.py` |
| `404` model not found | the model name changed: set `GEMINI_MODEL`, and edit `ROUTING` in your `prod.py` |
| `401` / `403` | the key is wrong: make a new one |
