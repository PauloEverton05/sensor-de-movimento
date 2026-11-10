# SENTINEL AI

Central local de vigilância com visão computacional: gravação contínua da webcam e de
câmeras IP, detecção de movimento e de pessoas, catálogo de pessoas autorizadas e
histórico de eventos. Processamento 100% local.

> **Estado atual: Fase 2 (infraestrutura).** Ainda não há captura de câmera nem gravação.
> Veja [PROJECT_STATUS.md](PROJECT_STATUS.md) e a arquitetura em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Plataformas

| Plataforma | Situação |
|---|---|
| Windows 11 x64 | Plataforma principal de desenvolvimento e teste em hardware |
| Linux x86_64 | Compila e testa no CI; teste em hardware planejado (pendrive live) |
| macOS | Compila e testa no CI. **Não suportado** (sem hardware para teste real) |
| Windows 10, ARM64 | **Não suportado** (sem hardware para teste real) |

## Desenvolvimento

Requisitos: [uv](https://docs.astral.sh/uv/). O uv instala o Python 3.12 automaticamente.

```powershell
uv sync                      # cria o ambiente e instala dependências
uv run sentinel-agent --console-log   # sobe o agente
uv run sentinel-ctl status   # em outro terminal: consulta o agente
uv run sentinel-ctl shutdown
```

Verificações (as mesmas do CI):

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
```

Empacotar o agente e testar o binário:

```powershell
uv run python scripts/build_agent.py
uv run python scripts/smoke_packaged_agent.py
```

## Licença

Software proprietário. Todos os direitos reservados. Dependências de terceiros em
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
