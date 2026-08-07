import pytest

from options_strategy import cli


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def test_missing_command_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", ["qa", "run", "sweep", "match", "report"])
def test_unimplemented_subcommands_exit_2(command: str) -> None:
    # Stubs; each is replaced by the real behavior test when its phase lands.
    assert cli.main([command]) == 2
