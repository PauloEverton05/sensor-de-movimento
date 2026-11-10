"""Logging estruturado (JSON Lines) com redação de dados sensíveis.

Regra (docs/ARQUITETURA.md §14): logs nunca contêm credenciais, URLs com senha,
tokens, imagens ou nomes de pessoas. A redação é uma rede de segurança; o código
continua responsável por não logar esses dados.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# rtsp://usuario:senha@host → rtsp://***:***@host
# A senha é gulosa até o ÚLTIMO "@" antes do caminho: usuários digitam senhas com "@"
# sem percent-encoding, e um "@" não guloso vazaria o restante da senha.
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s:@]+:[^/\s]+@")
_SENSITIVE_KEYS = frozenset(
    {"password", "passwd", "senha", "secret", "token", "authkey", "credential", "credentials"}
)
_REDACTED = "***"

# Atributos padrão de LogRecord que não devem ir para "extra".
_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


def redact_text(text: str) -> str:
    return _URL_CREDENTIALS.sub(r"\g<scheme>***:***@", text)


def redact_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(key, v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact_value(key, value)
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(
    logs_dir: Path,
    *,
    level: str = "INFO",
    retention_days: int = 30,
    console: bool = False,
    filename: str = "agent.log",
) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    formatter = JsonFormatter()
    file_handler = logging.handlers.TimedRotatingFileHandler(
        logs_dir / filename, when="midnight", backupCount=retention_days, encoding="utf-8", utc=True
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)
