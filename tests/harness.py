"""Differential/snapshot test harness.

A scenario is a list of steps (see scenarios.py). The harness plays a scenario
against a *tool* -- real yadm or pyadm -- inside a throwaway home directory and
produces a normalised, JSON-serialisable record of what happened:

* for every tool invocation: exit code, stdout and stderr
* the end state: files in the work tree, tracked files, HEAD, key Git config

Records produced by yadm are committed under tests/snapshots. pyadm must
reproduce them on every platform, and wherever yadm itself can run the
snapshots are re-verified against it so they can't silently drift.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

TESTS = Path(__file__).parent
SNAPSHOTS = TESTS / "snapshots"
SRC = TESTS.parent / "src"

YADM_VERSION = "3.5.0"
YADM_URL = f"https://raw.githubusercontent.com/yadm-dev/yadm/{YADM_VERSION}/yadm"
YADM_SHA256 = "d8c2d661725b98e9910e4a59b58beed5cfb01f5196a825a08668ff0887f7441d"

GIT_CONFIG = """\
[user]
	name = Test User
	email = test@example.com
[init]
	defaultBranch = main
[core]
	autocrlf = false
[commit]
	gpgsign = false
[protocol "file"]
	allow = always
"""
DATE = "2020-01-02T03:04:05+00:00"
REPO_CONFIGS = ("core.bare", "core.worktree", "status.showUntrackedFiles", "yadm.managed")


@dataclass(frozen=True)
class Tool:
    name: str
    argv: tuple


PYADM = Tool("pyadm", (sys.executable, "-m", "pyadm"))


def find_yadm() -> Tool | None:
    """Locate (downloading and caching if needed) the pinned yadm release."""
    bash = shutil.which("bash")
    if os.name == "nt" or not bash:
        return None
    script = os.environ.get("YADM_BIN")
    if not script:
        cached = TESTS / ".cache" / f"yadm-{YADM_VERSION}" / "yadm"
        if not cached.exists():
            try:
                with urllib.request.urlopen(YADM_URL, timeout=30) as response:
                    data = response.read()
            except OSError:
                return None
            if hashlib.sha256(data).hexdigest() != YADM_SHA256:
                raise RuntimeError(f"checksum mismatch for {YADM_URL}")
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        script = str(cached)
    return Tool("yadm", (bash, script))


def play(scenario: dict, tool: Tool, root: Path) -> dict:
    """Run a scenario against a tool in the (empty) directory root."""
    root = root.resolve()
    home = root / "home"
    home.mkdir()
    (root / "gitconfig").write_text(GIT_CONFIG)

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "XDG_", "YADM_", "LC_")) and key != "GNUPGHOME"
    }
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=str(root / "gitconfig"),
        GIT_AUTHOR_DATE=DATE,
        GIT_COMMITTER_DATE=DATE,
        GIT_TERMINAL_PROMPT="0",
        LC_ALL="C",
        TZ="UTC",
        PYTHONPATH=str(SRC),
    )

    def fill(text: str) -> str:
        return text.format(home=home.as_posix(), tmp=root.as_posix(), prog=tool.name)

    def normalise(text: str) -> str:
        for form in {str(root), root.as_posix()}:
            text = text.replace(form, "<TMP>")
        return re.sub(r"\bp?yadm\b", "<prog>", text)

    def run(argv, cwd):
        return subprocess.run(
            argv,
            cwd=fill(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            timeout=120,
        )

    record: dict = {"steps": []}
    for step in scenario["steps"]:
        kind, cwd = step[0], step[2] if len(step) > 2 and step[0] != "write" else "{home}"
        if kind == "write":
            path = Path(fill(step[1]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(step[2], newline="\n")
        elif kind == "git":  # unrecorded setup, e.g. building a remote
            result = run(["git", *map(fill, step[1])], "{tmp}")
            assert result.returncode == 0, result.stderr
        elif kind in ("run", "rc", "inspect"):
            if kind == "inspect":  # recorded plain git command
                result = run(["git", *map(fill, step[1])], "{tmp}")
            else:
                result = run([*tool.argv, *map(fill, step[1])], cwd)
            entry = {"args": [kind, *step[1]], "returncode": result.returncode}
            if kind != "rc":  # "rc" steps have output that legitimately differs
                entry["stdout"] = normalise(result.stdout)
                entry["stderr"] = normalise(result.stderr)
            record["steps"].append(entry)
        else:
            raise ValueError(kind)

    repo = Path(fill(scenario.get("repo", "{home}/.local/share/{prog}/repo.git")))
    work = Path(fill(scenario.get("work", "{home}")))
    record["files"] = files = {}
    record["private_dir_modes"] = modes = {}
    for directory, subdirs, names in os.walk(work):
        if Path(directory) == repo:
            subdirs.clear()
            continue
        for name in sorted(subdirs + names):
            path = Path(directory) / name
            key = normalise(path.relative_to(work).as_posix())
            if path.is_symlink():
                files[key] = "-> " + normalise(os.readlink(path))
            elif path.is_dir():
                files[key] = "<dir>"
                if name in (".ssh", ".gnupg"):
                    modes[key] = oct(stat.S_IMODE(path.stat().st_mode))
            else:
                files[key] = normalise(path.read_text(encoding="utf-8"))

    record["git"] = git = {}
    if repo.is_dir():
        env["GIT_DIR"] = str(repo)
        git["tracked"] = run(["git", "ls-files"], str(work)).stdout.splitlines()
        git["status"] = run(["git", "status", "--porcelain"], str(work)).stdout.splitlines()
        git["head"] = run(["git", "rev-parse", "--verify", "-q", "HEAD"], "{tmp}").stdout.strip()
        for key in REPO_CONFIGS:
            git[key] = normalise(run(["git", "config", "--get", key], "{tmp}").stdout.strip())
    return record


def comparable(record: dict) -> dict:
    """Drop the parts of a record that can't be reproduced on this platform."""
    record = dict(record)
    if os.name == "nt":  # no POSIX permission bits
        record.pop("private_dir_modes", None)
    return record


def snapshot_path(name: str) -> Path:
    return SNAPSHOTS / f"{name}.json"


def load_snapshot(name: str) -> dict:
    return json.loads(snapshot_path(name).read_text(encoding="utf-8"))


def save_snapshot(name: str, record: dict) -> None:
    SNAPSHOTS.mkdir(exist_ok=True)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    snapshot_path(name).write_text(text, encoding="utf-8", newline="\n")
