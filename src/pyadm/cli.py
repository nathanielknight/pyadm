# pyadm - a cross-platform Python clone of yadm
#
# Derived from yadm (https://github.com/yadm-dev/yadm)
# Copyright (C) 2015-2024 Tim Byrne
# Copyright (C) 2025 Erik Flodin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Command line interface.

The structure deliberately follows the yadm shell script (process global
switches, resolve paths, dispatch to an internal command or pass through to
Git) so the two can be compared side by side and tested differentially.
"""

from __future__ import annotations

import os
import platform
import random
import shutil
import stat
import subprocess
import sys

from pyadm import __version__

PROG = "pyadm"

# Commands implemented by pyadm itself. Anything else is passed to Git.
COMMANDS = ("clean", "clone", "config", "help", "init", "introspect", "list", "version")

# yadm commands that pyadm does not (yet) implement. They are rejected rather
# than being passed to Git, which would only produce a confusing error.
UNSUPPORTED = (
    "alt",
    "bootstrap",
    "decrypt",
    "encrypt",
    "enter",
    "git-crypt",
    "perms",
    "transcrypt",
    "upgrade",
)

CONFIGS = ("yadm.auto-private-dirs", "yadm.git-program")

# Global switches, mapped to the description used in error messages.
SWITCHES = {
    "--yadm-dir": "yadm",
    "-Y": "yadm",
    "--yadm-data": "data",
    "--yadm-repo": "repo",
    "--yadm-config": "config",
    # accepted for compatibility; the features they configure are not implemented
    "--yadm-encrypt": "encrypt",
    "--yadm-archive": "archive",
    "--yadm-bootstrap": "bootstrap",
}

LOCAL_OPTIONS = tuple(
    "local." + name
    for name in ("class", "arch", "os", "hostname", "user", "distro", "distro-family")
)


class Exit(Exception):
    """Unwind to main() and exit with the given code."""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


def out(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def error_out(text: str) -> "Exit":
    sys.stdout.flush()
    sys.stderr.write("ERROR: " + text + "\n")
    sys.stderr.flush()
    return Exit(1)


def norm(path: str) -> str:
    """Use forward slashes everywhere, as Git does on Windows."""
    return path.replace("\\", "/") if os.sep == "\\" else path


def qualify_path(path: str | None, what: str) -> str:
    if not path:
        raise error_out(f"You can't specify an empty {what} path")
    return norm(os.path.abspath(path))


def remove_tree(path: str) -> None:
    """rm -rf, including the read-only files Git creates on Windows."""

    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


class Pyadm:
    def __init__(self) -> None:
        self.home = norm(os.environ.get("HOME") or os.path.expanduser("~"))
        self.work = self.home
        self.dir = ""
        self.data = ""
        self.repo = ""
        self.config_file = ""
        self.overrides: dict[str, str] = {}
        self.git_program = "git"
        self.env = dict(os.environ)
        self.debug_enabled = False
        self.force = False
        self.list_all = False

    # ****** Setup ******

    def process_global_args(self, argv: list[str]) -> list[str]:
        """Remove global switches (wherever they appear) and return the rest."""
        main_args = []
        args = iter(argv)
        for arg in args:
            if arg in SWITCHES:
                self.overrides[SWITCHES[arg]] = qualify_path(next(args, None), SWITCHES[arg])
            else:
                main_args.append(arg)
        return main_args

    def configure_paths(self) -> None:
        def xdg(variable: str, default: str) -> str:
            base = os.environ.get(variable, "")
            return norm(base) if os.path.isabs(base) else f"{self.home}/{default}"

        self.dir = self.overrides.get("yadm") or xdg("XDG_CONFIG_HOME", ".config") + "/" + PROG
        self.data = self.overrides.get("data") or xdg("XDG_DATA_HOME", ".local/share") + "/" + PROG
        self.config_file = self.overrides.get("config") or self.dir + "/config"
        self.repo = self.overrides.get("repo") or self.data + "/repo.git"

        # use the pyadm repo for all git operations
        self.env["GIT_DIR"] = self.repo

        # obtain the work tree from the repo if it exists
        if os.path.isdir(self.repo) and shutil.which(self.git_program):
            work = self.git_output("config", "core.worktree")
            if work:
                self.work = work

    def require_git(self) -> None:
        more_info = ""
        alt_git = self.config_value("yadm.git-program") if shutil.which("git") else ""
        if alt_git:
            self.git_program = alt_git
            more_info = "\nThis command has been set via the yadm.git-program configuration."
        if not shutil.which(self.git_program):
            raise error_out(
                "This functionality requires Git to be installed, but the command "
                f"'{self.git_program}' cannot be located.{more_info}"
            )

    def require_repo(self) -> None:
        if not os.path.isdir(self.repo):
            raise error_out("Git repo does not exist. did you forget to run 'init' or 'clone'?")

    # ****** Helpers ******

    def debug(self, text: str) -> None:
        if self.debug_enabled:
            out("DEBUG: " + text)

    def git(self, *args: str, cwd: str | None = None) -> int:
        """Run Git with inherited stdio and return its exit code."""
        sys.stdout.flush()
        sys.stderr.flush()
        program = shutil.which(self.git_program) or self.git_program
        return subprocess.call([program, *args], env=self.env, cwd=cwd)

    def git_output(self, *args: str, cwd: str | None = None) -> str:
        """Run Git and return its stdout (stderr is discarded)."""
        program = shutil.which(self.git_program) or self.git_program
        result = subprocess.run(
            [program, *args],
            env=self.env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="surrogateescape",
        )
        return result.stdout.rstrip("\n")

    def config_value(self, *args: str) -> str:
        return self.git_output("config", "--file=" + self.config_file, *args)

    def private_dirs(self) -> list[str]:
        gnupghome = os.environ.get("GNUPGHOME")
        if not gnupghome:
            return [".ssh", ".gnupg"]
        try:
            return [".ssh", norm(os.path.relpath(gnupghome, self.work))]
        except ValueError:  # different drive on Windows
            return [".ssh"]

    def assert_private_dirs(self, *private_dirs: str) -> None:
        for private_dir in private_dirs:
            path = f"{self.work}/{private_dir}"
            if not os.path.isdir(path):
                self.debug(f"Creating {path}")
                try:
                    os.makedirs(path, mode=0o700)
                except OSError:
                    pass

    def remove_existing_repo(self, action: str) -> None:
        if os.path.isdir(self.repo):
            self.debug(f"Removing existing repo prior to {action}")
            self.git("-C", self.work, "submodule", "deinit", "-f", "--all")
            remove_tree(self.repo)

    def refuse_existing_repo(self) -> None:
        if os.path.isdir(self.repo) and not self.force:
            raise error_out(
                f"Git repo already exists. [{self.repo}]\n"
                "Use '-f' if you want to force it to be overwritten."
            )

    def configure_repo(self) -> None:
        self.debug("Configuring new repo")
        # change bare to false (there is a working directory)
        self.git("config", "core.bare", "false")
        # set the worktree for the repo
        self.git("config", "core.worktree", self.work)
        # by default, do not show untracked files and directories
        self.git("config", "status.showUntrackedFiles", "no")
        # marks the repo as managed (same key as yadm)
        self.git("config", "yadm.managed", "true")

    # ****** Commands ******

    def cmd_clean(self, args: list[str]) -> None:
        raise error_out(
            '"git clean" has been disabled for safety. '
            "You could end up removing all unmanaged files."
        )

    def cmd_clone(self, args: list[str]) -> None:
        clone_args: list[str] = []
        do_checkout = True
        submodules: list[str] = []
        remaining = iter(args)
        for arg in remaining:
            if arg in ("--bootstrap", "--no-bootstrap"):
                pass  # bootstrap is not implemented; accepted for compatibility
            elif arg == "--checkout":
                do_checkout = True
            elif arg in ("-n", "--no-checkout"):
                do_checkout = False
            elif arg in ("--recursive", "--recurse-submodules"):
                submodules.append(":/")
            elif arg.startswith("--recurse-submodules="):
                submodules.append(":/" + arg.split("=", 1)[1])
            elif arg in ("--bare", "--mirror") or arg.startswith("--separate-git-dir="):
                pass  # these would break the repo layout pyadm relies on
            elif arg == "--separate-git-dir":
                next(remaining, None)
            else:
                clone_args.append(arg)

        # safety check, don't attempt to clone when the repo is already present
        self.refuse_existing_repo()
        self.remove_existing_repo("clone")

        tmp = f"{self.data}/tmp.{os.getpid()}.{random.randrange(32768)}"
        try:
            os.makedirs(tmp)
        except OSError:
            raise error_out("Unable to create temporary directory") from None

        # first clone without checkout
        self.debug("Doing an initial clone of the repository")
        failed = self.git(
            "-c",
            "core.sharedrepository=0600",
            "clone",
            "--no-checkout",
            "--separate-git-dir=" + self.repo,
            *clone_args,
            "repo.git",
            cwd=tmp,
        )
        if failed:
            self.debug("Removing repo after failed clone")
            for path in (self.repo, tmp):
                if os.path.isdir(path):
                    remove_tree(path)
            raise error_out("Unable to clone the repository")
        self.configure_repo()
        remove_tree(tmp)

        # then reset the index as the --no-checkout flag makes the index empty
        self.git("reset", "--quiet", "--", ":/")

        if self.work == self.home:
            self.debug("Determining if repo tracks private directories")
            for private_dir in self.private_dirs():
                if self.git_output("log", "-n", "1", "--", private_dir):
                    self.debug(f"Private directory {private_dir} is tracked by repo")
                    self.assert_private_dirs(private_dir)

        # finally check out (unless instructed not to) all files that don't
        # exist in the work tree
        if not do_checkout:
            return
        if not os.path.isdir(self.work):
            self.debug(f"Clone not processed, unable to cd to {self.work}")
            return

        deleted = self.git_output("ls-files", "-z", "--deleted", cwd=self.work)
        for path in filter(None, deleted.split("\0")):
            self.git("checkout", "--", ":/" + path, cwd=self.work)

        if submodules:
            self.git("submodule", "update", "--init", "--recursive", "--", *submodules, cwd=self.work)

        if self.git_output("ls-files", "--modified", cwd=self.work):
            out(
                "**NOTE**\n"
                "  Local files with content that differs from the ones just\n"
                f"  cloned were found in {self.work}. They have been left\n"
                "  unmodified.\n"
                "\n"
                "  Please review and resolve any differences appropriately.\n"
                "  If you know what you're doing, and want to overwrite the\n"
                f"  tracked files, consider '{PROG} checkout \"{self.work}\"'.\n"
            )

    def cmd_config(self, args: list[str]) -> int:
        if not args:
            # with no parameters, provide some helpful documentation
            out(f"{PROG} supports the following configurations:")
            out()
            for name in CONFIGS:
                out("  " + name)
            out()
            out("Please read the README for more details about configurations,")
            out("and how to adjust them.")
            return 0
        if any(arg in LOCAL_OPTIONS for arg in args):
            # operate on the repo's configuration, which is always local to
            # the machine
            self.require_repo()
            return self.git("config", *args)
        # operate on the pyadm configuration file
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        return self.git("config", "--file=" + self.config_file, *args)

    def cmd_help(self, args: list[str]) -> None:
        def row(path: str) -> str:
            return path.replace(self.home, "$HOME", 1).ljust(32)

        out(
            f"""Usage: {PROG} <command> [options...]

Manage dotfiles maintained in a Git repository.

Git Commands:
Any Git command or alias can be used as a <command>. It will operate
on {PROG}'s repository and files in the work tree (usually $HOME).

Commands:
  {PROG} init [-f]             - Initialize an empty repository
  {PROG} clone <url> [-f]      - Clone an existing repository
  {PROG} config <name> <value> - Configure a setting
  {PROG} list [-a]             - List tracked files
  {PROG} gitconfig [OPTIONS]   - Run "git config" for the {PROG} repo
  {PROG} version               - Show version information

Files:
  {row(self.config_file)} - {PROG}'s configuration file
  {row(self.repo)} - {PROG}'s Git repository"""
        )
        raise Exit(1)

    def cmd_init(self, args: list[str]) -> None:
        # safety check, don't attempt to init when the repo is already present
        self.refuse_existing_repo()
        self.remove_existing_repo("init")

        # init a new bare repo
        self.debug("Init new repo")
        self.git("init", "--shared=0600", "--bare", self.repo, *args)
        self.configure_repo()

    def cmd_introspect(self, args: list[str]) -> None:
        # like yadm, the lists have no trailing newline
        topic = args[0] if args else ""
        if topic == "commands":
            sys.stdout.write("\n".join(sorted(COMMANDS + ("gitconfig",))))
        elif topic == "configs":
            sys.stdout.write("\n".join(CONFIGS))
        elif topic == "repo":
            out(self.repo)
        elif topic == "switches":
            sys.stdout.write("\n".join(sorted(SWITCHES)))

    def cmd_list(self, args: list[str]) -> None:
        self.require_repo()
        # process relative to the work tree when -a is specified
        cwd = None
        if self.list_all:
            if not os.path.isdir(self.work):
                self.debug(f"List not processed, unable to cd to {self.work}")
                return
            cwd = self.work
        self.git("ls-files", cwd=cwd)

    def cmd_version(self, args: list[str]) -> None:
        git_version = self.git_output("--version")
        out(f"python version {platform.python_version()}")
        out(f"   {git_version}")
        out(f" {PROG} version {__version__}")

    def git_command(self, args: list[str]) -> int:
        self.require_repo()

        # translate 'gitconfig' to 'config' -- 'config' is reserved for pyadm
        if args[0] == "gitconfig":
            args = ["config", *args[1:]]

        # ensure private .ssh and .gnupg directories exist first
        if self.work == self.home:
            if self.config_value("--bool", "yadm.auto-private-dirs") != "false":
                self.assert_private_dirs(*self.private_dirs())

        # pass commands through to git
        self.debug(f"Running git command {self.git_program} {' '.join(args)}")
        return self.git(*args)

    # ****** Main ******

    def run(self, argv: list[str]) -> int:
        args = self.process_global_args(argv)
        self.configure_paths()
        self.require_git()

        # create the config and data directories if they don't exist yet
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.data, exist_ok=True)

        if not args:
            self.cmd_help([])
        command = args[0]
        if command in UNSUPPORTED:
            raise error_out(f"The '{command}' command is not supported by {PROG}.")
        if command not in COMMANDS + ("--help", "--version"):
            # any other commands are simply passed through to git
            return self.git_command(args)

        command_args = []
        rest = iter(args[1:])
        for arg in rest:
            if arg == "-a":  # used by list
                self.list_all = True
            elif arg == "-d":  # used by all commands
                self.debug_enabled = True
            elif arg == "-f":  # used by init and clone
                self.force = True
            elif arg == "-l":
                if command in ("clone", "config"):
                    command_args.append(arg)
            elif arg == "-w":  # used by init and clone
                self.work = qualify_path(next(rest, None), "work tree")
            else:
                command_args.append(arg)

        if not os.path.isdir(self.work):
            raise error_out(f"Work tree does not exist: [{self.work}]")
        # like yadm, internal commands exit 0 unless they report an error
        # themselves; the exit status of Git is not propagated
        getattr(self, "cmd_" + command.lstrip("-"))(command_args)
        return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return Pyadm().run(list(sys.argv[1:] if argv is None else argv))
    except Exit as exc:
        return exc.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
