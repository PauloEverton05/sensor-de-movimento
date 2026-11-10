import json
import logging
from pathlib import Path

from sentinel.common.logging import JsonFormatter, redact_text, redact_value, setup_logging


def test_redacts_credentials_in_urls() -> None:
    text = "abrindo rtsp://admin:S3nh@!@192.168.0.10:554/stream1"
    out = redact_text(text)
    assert "admin" not in out
    assert "S3nh" not in out
    assert "rtsp://***:***@192.168.0.10:554/stream1" in out


def test_url_without_credentials_untouched() -> None:
    assert redact_text("rtsp://192.168.0.10/stream") == "rtsp://192.168.0.10/stream"


def test_sensitive_keys_redacted_recursively() -> None:
    value = {"camera": {"password": "x", "url": "http://u:p@h/"}, "token": "abc"}
    out = redact_value("extra", value)
    assert out == {"camera": {"password": "***", "url": "http://***:***@h/"}, "token": "***"}


def test_json_formatter_applies_redaction_to_extra() -> None:
    record = logging.makeLogRecord(
        {
            "msg": "conectando %s",
            "args": ("rtsp://a:b@h",),
            "levelname": "INFO",
            "name": "t",
            "password": "segredo",
        }
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["msg"] == "conectando rtsp://***:***@h"
    assert payload["password"] == "***"


def test_setup_logging_writes_json_lines(tmp_path: Path) -> None:
    setup_logging(tmp_path, level="INFO")
    logging.getLogger("x").info("olá", extra={"camera_id": "c1"})
    for h in logging.getLogger().handlers:
        h.flush()
    line = (tmp_path / "agent.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["msg"] == "olá"
    assert payload["camera_id"] == "c1"
    for h in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(h)
        h.close()
