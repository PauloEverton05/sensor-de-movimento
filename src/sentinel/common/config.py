"""Configuração de bootstrap do agente (configuration/agent.toml).

Só o mínimo necessário para o agente subir. Todas as demais configurações
ficam no banco (tabela settings), que é a fonte oficial.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class BootstrapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    log_level: LogLevel = "INFO"
    log_retention_days: int = Field(default=30, ge=1, le=365)


def load_bootstrap_config(path: Path) -> BootstrapConfig:
    if not path.exists():
        return BootstrapConfig()
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return BootstrapConfig.model_validate(data)
