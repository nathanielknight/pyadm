"""Scenarios played against both yadm and pyadm.

Each scenario is a dict with a list of "steps":

    ("run", [args...], cwd?)  run the tool; exit code and output are compared
    ("rc", [args...], cwd?)   run the tool; only the exit code is compared
                              (for output that intentionally differs)
    ("write", path, content)  create a file
    ("git", [args...])        run plain git as setup (must succeed, not recorded)
    ("inspect", [args...])    run plain git and compare its output

Strings may use {home}, {tmp} (scratch space outside the home directory) and
{prog} (the tool's name). "repo"/"work" say where the end state is found when a
scenario moves them from their defaults.
"""

# builds a remote at {tmp}/remote.git containing two dotfiles
REMOTE = [
    ("git", ["init", "-q", "{tmp}/seed"]),
    ("write", "{tmp}/seed/.vimrc", "set number\n"),
    ("write", "{tmp}/seed/.config/app/settings.ini", "[app]\ncolor = blue\n"),
    ("git", ["-C", "{tmp}/seed", "add", "."]),
    ("git", ["-C", "{tmp}/seed", "commit", "-q", "-m", "seed"]),
    ("git", ["clone", "-q", "--bare", "{tmp}/seed", "{tmp}/remote.git"]),
]

SCENARIOS = {
    "init_add_commit": {
        "steps": [
            ("run", ["init"]),
            ("write", "{home}/.bashrc", "export EDITOR=vim\n"),
            ("write", "{home}/.config/app/my settings.ini", "[app]\n"),
            ("write", "{home}/untracked.txt", "not tracked\n"),
            ("run", ["add", ".bashrc", ".config/app/my settings.ini"]),
            ("run", ["status", "--short"]),
            ("run", ["commit", "-m", "first commit"]),
            ("run", ["list"]),
            ("run", ["list", "-a"], "{home}/.config"),
            ("run", ["list"], "{home}/.config"),
            ("write", "{home}/.bashrc", "export EDITOR=nano\n"),
            ("run", ["diff", "--stat"]),
            ("run", ["commit", "-a", "-m", "second commit"]),
            ("run", ["log", "--format=%H %s"]),
        ],
    },
    "init_existing": {
        "steps": [
            ("run", ["init"]),
            ("write", "{home}/.bashrc", "export EDITOR=vim\n"),
            ("run", ["add", ".bashrc"]),
            ("run", ["init"]),
            ("run", ["list"]),
            ("run", ["init", "-f"]),
            ("run", ["list"]),
        ],
    },
    "init_worktree": {
        "work": "{tmp}/work",
        "steps": [
            ("run", ["init", "-w", "{tmp}/missing"]),
            ("write", "{tmp}/work/file.txt", "content\n"),
            ("run", ["init", "-w", "{tmp}/work"]),
            ("run", ["add", "{tmp}/work/file.txt"]),
            ("run", ["commit", "-q", "-m", "work"]),
            ("run", ["list", "-a"]),
        ],
    },
    "no_repo": {
        "steps": [
            ("run", ["status"]),
            ("run", ["list"]),
            ("run", ["add", "foo"]),
            ("run", ["gitconfig", "core.bare"]),
            ("run", ["clean"]),
            ("run", ["introspect", "repo"]),
            ("run", ["introspect", "switches"]),
            ("run", ["introspect", "bogus"]),
            ("rc", []),
            ("rc", ["help"]),
            ("rc", ["--help"]),
            ("rc", ["version"]),
            ("rc", ["--version"]),
        ],
    },
    "config": {
        "steps": [
            ("run", ["config", "yadm.auto-private-dirs", "false"]),
            ("run", ["config", "yadm.auto-private-dirs"]),
            ("run", ["config", "--bool", "yadm.auto-private-dirs"]),
            ("run", ["config", "missing.key"]),
            ("run", ["config", "local.class", "work"]),
            ("run", ["init"]),
            ("run", ["config", "local.class", "work"]),
            ("run", ["config", "local.class"]),
            ("run", ["gitconfig", "local.class"]),
            ("run", ["gitconfig", "core.bare"]),
            ("run", ["gitconfig", "missing.key"]),
            ("run", ["config", "-l"]),
            ("run", ["status", "--short"]),
        ],
    },
    "overrides": {
        "repo": "{tmp}/custom/repo",
        "steps": [
            ("run", ["-Y", "{tmp}/custom/dir", "--yadm-repo", "{tmp}/custom/repo", "init"]),
            ("run", ["status"]),
            ("write", "{home}/.profile", "umask 022\n"),
            ("run", ["--yadm-repo", "{tmp}/custom/repo", "add", ".profile"]),
            ("run", ["commit", "--yadm-repo", "{tmp}/custom/repo", "-m", "anywhere"]),
            ("run", ["--yadm-repo", "{tmp}/custom/repo", "introspect", "repo"]),
            ("run", ["--yadm-data", "{tmp}/custom/data", "introspect", "repo"]),
            ("run", ["--yadm-config", "{tmp}/custom/cfg", "config", "a.b", "c"]),
            ("inspect", ["config", "--file", "{tmp}/custom/cfg", "a.b"]),
        ],
    },
    "clone": {
        "steps": REMOTE
        + [
            ("run", ["clone", "{tmp}/remote.git"]),
            ("run", ["list"]),
            ("run", ["status", "--short", "--branch"]),
            ("run", ["clone", "{tmp}/remote.git"]),
            ("write", "{home}/.vimrc", "set nonumber\n"),
            ("run", ["clone", "-f", "{tmp}/remote.git"]),
            ("run", ["status", "--short"]),
        ],
    },
    "clone_local_differences": {
        "steps": REMOTE
        + [
            ("write", "{home}/.vimrc", "my local vimrc\n"),
            ("run", ["clone", "{tmp}/remote.git"]),
            ("run", ["status", "--short"]),
            ("run", ["checkout", "{home}"]),
            ("run", ["status", "--short"]),
        ],
    },
    "clone_options": {
        "work": "{tmp}/work",
        "steps": REMOTE
        + [
            ("git", ["init", "-q", "{tmp}/work"]),
            ("run", ["clone", "--bare", "--no-checkout", "-w", "{tmp}/work", "{tmp}/remote.git"]),
            ("run", ["status", "--short"]),
            ("run", ["clone", "-f", "--no-bootstrap", "-b", "main", "{tmp}/remote.git"]),
        ],
    },
    "clone_failure": {
        "steps": [
            ("run", ["clone", "{tmp}/does-not-exist.git"]),
            ("run", ["list"]),
        ],
    },
    "push_pull": {
        "steps": REMOTE
        + [
            ("run", ["clone", "{tmp}/remote.git"]),
            ("write", "{home}/.vimrc", "set number\nset ruler\n"),
            ("write", "{home}/.zshrc", "setopt autocd\n"),
            ("run", ["add", ".vimrc", ".zshrc"]),
            ("run", ["commit", "-q", "-m", "from home"]),
            ("run", ["push"]),
            ("inspect", ["--git-dir={tmp}/remote.git", "log", "--format=%H %s"]),
            # another machine pushes a change
            ("git", ["clone", "-q", "{tmp}/remote.git", "{tmp}/other"]),
            ("write", "{tmp}/other/.tmux.conf", "set -g mouse on\n"),
            ("git", ["-C", "{tmp}/other", "add", "."]),
            ("git", ["-C", "{tmp}/other", "commit", "-q", "-m", "from other"]),
            ("git", ["-C", "{tmp}/other", "push", "-q"]),
            ("run", ["pull"]),
            ("run", ["log", "--format=%H %s"]),
            ("run", ["list"]),
        ],
    },
}
