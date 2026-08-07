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


def test_qa_requires_world_argument() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["qa"])
    assert exc.value.code == 2


def test_worldgen_requires_config_argument() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["worldgen"])
    assert exc.value.code == 2


def test_sweep_requires_config_argument() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["sweep"])
    assert exc.value.code == 2


@pytest.mark.parametrize("command", ["run", "match", "report"])
def test_unimplemented_subcommands_exit_2(command: str) -> None:
    # Stubs; each is replaced by the real behavior test when its phase lands.
    assert cli.main([command]) == 2
