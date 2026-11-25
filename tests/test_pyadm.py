"""Behaviour that is specific to pyadm, where it intentionally differs from yadm."""

import harness


def run(tmp_path, *commands):
    steps = [("run", list(command)) for command in commands]
    return harness.play({"steps": steps}, harness.PYADM, tmp_path)["steps"]


def test_unsupported_commands_are_rejected(tmp_path):
    for step in run(tmp_path, ["init"], ["enter"], ["alt"], ["encrypt"], ["bootstrap"]):
        if step["args"][1] != "init":
            assert step["returncode"] == 1
            assert "not supported" in step["stderr"]


def test_help(tmp_path):
    for step in run(tmp_path, [], ["help"], ["--help"]):
        assert step["returncode"] == 1
        assert step["stdout"].startswith("Usage: <prog> <command>")
        assert "$HOME/.local/share/<prog>/repo.git" in step["stdout"]


def test_version(tmp_path):
    for step in run(tmp_path, ["version"], ["--version"]):
        assert step["returncode"] == 0
        python, git, prog = step["stdout"].splitlines()
        assert python.startswith("python version ")
        assert git.strip().startswith("git version ")
        assert prog.strip().startswith("<prog> version ")


def test_introspect(tmp_path):
    commands, configs = run(tmp_path, ["introspect", "commands"], ["introspect", "configs"])
    assert commands["stdout"].split() == [
        "clean", "clone", "config", "gitconfig", "help", "init", "introspect", "list", "version",
    ]  # fmt: skip
    assert configs["stdout"].split() == ["<prog>.auto-private-dirs", "<prog>.git-program"]


def test_empty_path_switch_is_an_error(tmp_path):
    # yadm reports the error but carries on; pyadm stops
    for step in run(tmp_path, ["--yadm-repo", "", "list"], ["--yadm-repo"]):
        assert step["returncode"] == 1
        assert step["stdout"] == ""
        assert step["stderr"] == "ERROR: You can't specify an empty repo path\n"


def test_git_program_config(tmp_path):
    steps = run(tmp_path, ["config", "yadm.git-program", "no-such-git"], ["init"])
    assert steps[1]["returncode"] == 1
    assert "'no-such-git' cannot be located" in steps[1]["stderr"]
