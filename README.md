# pyadm

A cross-platform Python clone of [yadm](https://yadm.io) (Yet Another Dotfiles
Manager). It manages your dotfiles in a bare Git repository whose work tree is
your home directory, and runs natively on Linux, macOS and Windows: the only
requirements are Python 3.9+ and Git. There are no other dependencies.

```
pyadm init                      # or: pyadm clone <url>
pyadm add ~/.bashrc ~/.config/nvim
pyadm commit -m "Add dotfiles"
pyadm remote add origin <url>
pyadm push -u origin main
pyadm pull
```

Any command pyadm doesn't know is passed to Git, operating on pyadm's
repository, so `pyadm status`, `pyadm diff`, `pyadm log` and so on all work
from any directory.

## Install

```
uv tool install git+https://github.com/nathanielknight/pyadm
# or: pipx install git+https://github.com/nathanielknight/pyadm
```

## Commands

| Command | |
| --- | --- |
| `pyadm init [-f] [-w <dir>]` | Initialize an empty repository |
| `pyadm clone <url> [-f] [-w <dir>]` | Clone an existing repository. Files that already exist locally are left untouched |
| `pyadm <git command>` | Run any Git command against the repository |
| `pyadm list [-a]` | List tracked files (under the current directory, or all) |
| `pyadm config <name> [<value>]` | Read or write pyadm's own configuration |
| `pyadm gitconfig ...` | `git config` for the repository (`config` is taken) |
| `pyadm introspect <commands\|configs\|repo\|switches>` | Machine-readable information |
| `pyadm version`, `pyadm help` | |

`pyadm clean` is disabled, as in yadm, because it would remove every
untracked file in your home directory.

Files live in the same layout as yadm, under pyadm's own name (so the two
never collide), on every platform:

| | |
| --- | --- |
| `~/.config/pyadm/config` | pyadm's configuration (`$XDG_CONFIG_HOME` is honoured) |
| `~/.local/share/pyadm/repo.git` | the Git repository (`$XDG_DATA_HOME` is honoured) |

The switches (`-Y`/`--yadm-dir`, `--yadm-data`, `--yadm-repo`,
`--yadm-config`) and configuration keys keep yadm's names:

* `yadm.auto-private-dirs` (default true): create `~/.ssh` and `~/.gnupg` with
  mode 0700 before running Git commands
* `yadm.git-program`: the Git executable to use

## Differences from yadm

Not implemented (yet): alternates and templates, `bootstrap`, hooks,
`encrypt`/`decrypt`, `perms`, `enter`, `git-crypt`, `transcrypt`, `upgrade`
and shell completions. Those commands report an error instead of being passed
to Git. There is no migration of an existing yadm repository.

Otherwise pyadm aims to behave exactly as yadm 3.5.0 does, including its
quirks (for instance, `config` and `init` exit 0 even when Git fails). The
exception is an empty path given to a switch such as `--yadm-repo`: yadm
reports the error and carries on, pyadm stops.

## Testing

```
uv run pytest
```

pyadm is tested differentially against real yadm. `tests/scenarios.py` holds
scenarios: sequences of commands, with some file and remote setup in between.
The harness (`tests/harness.py`) plays a scenario in a throwaway home directory
with a fixed Git identity and dates, so commit hashes are reproducible, and
records for each command the exit code, stdout and stderr, and at the end the
files in the work tree, the tracked files, `HEAD` and key Git configuration.
Temporary paths and the program name are normalised.

* Records made by yadm are committed in `tests/snapshots`.
* `test_pyadm_matches_snapshot` requires pyadm to reproduce them. This runs
  everywhere, including Windows, where yadm itself can't run natively.
* `test_snapshot_matches_yadm` replays the scenarios against the pinned yadm
  release wherever bash is available (it is downloaded to `tests/.cache`, or
  set `YADM_BIN`), so the snapshots can't drift from the real thing. It is
  skipped when yadm is unavailable, unless `PYADM_REQUIRE_YADM` is set.

After adding or changing a scenario, re-record with
`uv run pytest --update-snapshots`.

## License

GPL-3.0-or-later, like yadm, from which pyadm is derived.
