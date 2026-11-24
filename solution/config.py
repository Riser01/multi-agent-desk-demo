"""This file loads your own keys from a `.env` file into the environment, so no key ever appears in code. PROVIDED.

The demo needs at most a few secrets: a Gemini key for live runs, and optionally Langfuse keys for the trace viewer.
Secrets written into source code get committed and shared by accident. A git-ignored `.env` file keeps them on your
machine only, and this tiny loader reads it. It uses the standard library only (no python-dotenv).

It is the same loader as last week. Scripts call load_env() once, in their `if __name__ == "__main__":` block.
Library code reads os.environ only, so the tests never depend on whatever `.env` happens to be on disk.

What to look at in load_env()
    Your shell wins     a variable already set in your shell is kept over the file (setdefault), so
                        `export GEMINI_API_KEY=...` still works.
    Blanks are ignored  an unfilled `.env` behaves the same as no keys at all.
    Names, not values   it returns the names it set and never the values, so nothing secret gets printed.
"""
import os
from pathlib import Path


def load_env(path: "str | Path | None" = None) -> list[str]:
    """Read KEY=VALUE lines from `.env` (next to this file by default). Returns the names it set, never the values."""
    env_path = Path(path) if path else Path(__file__).with_name(".env")
    if not env_path.is_file():
        return []
    loaded: list[str] = []
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    # Langfuse's newer name is LANGFUSE_BASE_URL, older SDK versions read LANGFUSE_HOST: make either one work.
    if os.environ.get("LANGFUSE_BASE_URL") and not os.environ.get("LANGFUSE_HOST"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]
    return loaded
