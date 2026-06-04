import json

from deep6v2.logging import configure_logging, get_logger


def test_json_logging_output(capsys):
    configure_logging(dev_mode=False)
    log = get_logger("test")
    log.info("test_event", bar_index=42)

    output = capsys.readouterr().out.strip()
    data = json.loads(output)

    assert data["event"] == "test_event"
    assert data["bar_index"] == 42
    assert data["module"] == "test"
    assert data["level"] == "info"


def test_dev_logging_output(capsys):
    configure_logging(dev_mode=True)
    log = get_logger("test.dev")
    log.info("dev_event", value=123)

    output = capsys.readouterr().out.strip()
    assert output
    assert "dev_event" in output


def test_configure_logging_idempotent():
    configure_logging(dev_mode=False)
    configure_logging(dev_mode=False)
