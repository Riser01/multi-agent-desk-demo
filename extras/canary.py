"""W7-7b (stretch): a canary flag and a one-step rollback, for a new version of the team.

Changing a prompt or a model changes behaviour for everyone at once, unless you roll it out slowly. A canary sends a
small, fixed share of users to the new version while everyone else stays on the stable one. If the new version
misbehaves (the alerts in extras/monitor.py fire), one command puts every user back on stable: that is the rollback.

Two details make this work in practice, and this file shows both:
    sticky buckets   a user's bucket comes from a hash of their id, not a coin flip, so the same user always gets the
                     same version and a bug report can be reproduced.
    one switch       the rollout lives in one small file, data/rollout.json. Rollback is setting canary_percent to 0;
                     no code changes, no redeploy.

Run:  python extras/canary.py --users 10          who gets which version
      python extras/canary.py --set 25            send 25% to the canary
      python extras/canary.py --rollback          everyone back on stable
"""
import argparse
import hashlib
import json
import os
import sys

ROLLOUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "rollout.json")
DEFAULT = {"stable": {"app": "1.0.0", "routing": "prod.ROUTING"},
           "canary": {"app": "1.1.0", "routing": "planner on the cheap model (to test: does the plan quality hold?)"},
           "canary_percent": 10}


def bucket(user_id: str) -> int:
    """A sticky bucket 0..99 from a hash of the user id: the same user always lands in the same bucket."""
    return int(hashlib.sha256(user_id.encode()).hexdigest(), 16) % 100


def pick(user_id: str, rollout: dict) -> str:
    """'canary' for users whose bucket is under canary_percent, else 'stable'."""
    return "canary" if bucket(user_id) < rollout.get("canary_percent", 0) else "stable"


def load(path: str = ROLLOUT_PATH) -> dict:
    """The rollout file, or the default when it does not exist yet."""
    if not os.path.isfile(path):
        return dict(DEFAULT)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save(rollout: dict, path: str = ROLLOUT_PATH) -> None:
    """Write the rollout file. This one write is the whole deploy (and the whole rollback)."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rollout, handle, indent=1)


def main(argv=None, path: str = ROLLOUT_PATH, out=print) -> int:
    """Show assignments, change the canary share, or roll back."""
    parser = argparse.ArgumentParser(description="Canary flag and rollback for the desk team.")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--set", type=int, help="canary percent, 0 to 100")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    rollout = load(path)
    if args.rollback:
        rollout["canary_percent"] = 0
        save(rollout, path)
        out("rollback: canary_percent = 0, every user is on stable " + rollout["stable"]["app"])
    elif args.set is not None:
        rollout["canary_percent"] = max(0, min(100, args.set))
        save(rollout, path)
        out(f"rollout: {rollout['canary_percent']}% of users on canary {rollout['canary']['app']}")
    users = [f"user-{n:03d}" for n in range(1, args.users + 1)]
    for user in users:
        version = pick(user, rollout)
        out(f"{user}  bucket {bucket(user):>2}  ->  {version} ({rollout[version]['app']})")
    share = sum(pick(u, rollout) == "canary" for u in users)
    out(f"canary share: {share} of {len(users)} users (target {rollout['canary_percent']}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
