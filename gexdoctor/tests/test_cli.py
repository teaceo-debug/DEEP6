from __future__ import annotations

from pathlib import Path

import pytest

from gexdoctor import launch


def _write_config(path: Path, *, include_key: bool = True) -> Path:
    content = [
        "interval: 15",
        "source: QQQ",
        f"output_path: {path.parent.as_posix()}/gex_nq.json",
        "log_dir: logs",
        "min_confidence: 0.65",
        "anti_flicker_margin: 0.12",
        "massive_api_key: ''",
    ]
    if include_key:
        content.insert(0, "flashalpha_api_key: test-key")
    path.write_text("\n".join(content) + "\n", encoding="utf-8")
    return path


def test_build_parser_has_all_flags():
    parser = launch.build_parser()
    flags = {opt for action in parser._actions for opt in action.option_strings}
    for flag in ["--dry-run", "--once", "--interval", "--output", "--verbose", "-v", "--source", "--config"]:
        assert flag in flags


def test_help_shows_flags(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["gexdoctor", "--help"])
    with pytest.raises(SystemExit) as exc:
        launch.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--once" in out
    assert "--interval" in out
    assert "--source" in out


def test_validate_config_with_key(tmp_path: Path):
    config_path = _write_config(tmp_path / "config.yaml", include_key=True)
    valid, errors = launch.validate_config(config_path, {})
    assert valid is True
    assert errors == []


def test_validate_config_missing_key(tmp_path: Path):
    config_path = _write_config(tmp_path / "config.yaml", include_key=False)
    valid, errors = launch.validate_config(config_path, {})
    assert valid is False
    assert errors and "FLASHALPHA_API_KEY" in errors[0]


def test_dry_run_exits_zero(monkeypatch, tmp_path: Path, capsys):
    config_path = _write_config(tmp_path / "config.yaml", include_key=True)
    monkeypatch.setattr("sys.argv", ["gexdoctor", "--dry-run", "--config", str(config_path)])
    assert launch.main() == 0
    out = capsys.readouterr()
    assert "OK" in out.out
    assert out.err == ""


def test_dry_run_missing_key_exits_one(monkeypatch, tmp_path: Path, capsys):
    config_path = _write_config(tmp_path / "config.yaml", include_key=False)
    monkeypatch.setattr("sys.argv", ["gexdoctor", "--dry-run", "--config", str(config_path)])
    assert launch.main() == 1
    out = capsys.readouterr()
    assert "FLASHALPHA" in out.err
