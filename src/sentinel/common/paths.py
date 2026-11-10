"""Localização dos dados e dos arquivos de execução.

- Diretório de dados (SENTINEL_DATA): banco, gravações, logs… Pode ficar em outro disco.
- Diretório de execução: token, lock e socket. Sempre num local privado do usuário,
  mesmo quando o diretório de dados está num disco externo com permissões amplas.

Variáveis de ambiente (usadas principalmente pelos testes):
- SENTINEL_DATA_DIR: substitui o diretório de dados padrão.
- SENTINEL_RUNTIME_DIR: substitui a base do diretório de execução.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "SentinelAI"


def default_data_dir() -> Path:
    env = os.environ.get("SENTINEL_DATA_DIR")
    if env:
        return Path(env)
    return platformdirs.user_data_path(APP_NAME, appauthor=False, roaming=False)


def _runtime_base() -> Path:
    env = os.environ.get("SENTINEL_RUNTIME_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        # %LOCALAPPDATA%\SentinelAI\run — herda a ACL privada do perfil do usuário.
        return platformdirs.user_data_path(APP_NAME, appauthor=False) / "run"
    return platformdirs.user_runtime_path(APP_NAME)


def _instance_id(data_dir: Path) -> str:
    """Identificador curto e estável por diretório de dados (permite instâncias isoladas)."""
    digest = hashlib.sha256(str(data_dir.resolve()).lower().encode("utf-8")).hexdigest()
    return digest[:12]


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    runtime_dir: Path
    instance_id: str

    @classmethod
    def resolve(cls, data_dir: Path | None = None) -> AppPaths:
        data = (data_dir or default_data_dir()).resolve()
        iid = _instance_id(data)
        return cls(data_dir=data, runtime_dir=_runtime_base() / iid, instance_id=iid)

    # ---------------------------------------------------------- dados
    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def database_file(self) -> Path:
        return self.database_dir / "sentinel.db"

    @property
    def configuration_dir(self) -> Path:
        return self.data_dir / "configuration"

    @property
    def bootstrap_config_file(self) -> Path:
        return self.configuration_dir / "agent.toml"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    # ---------------------------------------------------------- execução
    @property
    def token_file(self) -> Path:
        return self.runtime_dir / "agent.token"

    @property
    def lock_file(self) -> Path:
        return self.runtime_dir / "agent.lock"

    @property
    def ipc_address(self) -> str:
        if sys.platform == "win32":
            user = os.environ.get("USERNAME", "user")
            safe_user = "".join(c for c in user if c.isalnum()) or "user"
            return rf"\\.\pipe\sentinel-ai-{safe_user}-{self.instance_id}"
        return str(self.runtime_dir / "agent.sock")

    def ensure(self) -> None:
        """Cria os diretórios necessários. O diretório de execução fica com modo 0700."""
        for d in (self.database_dir, self.configuration_dir, self.logs_dir, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            self.runtime_dir.chmod(0o700)
