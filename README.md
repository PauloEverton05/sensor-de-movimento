# SENTINEL AI

Central local de vigilância com visão computacional: gravação contínua da webcam e de
câmeras IP, detecção de movimento e de pessoas, catálogo de pessoas autorizadas e
histórico de eventos. Processamento 100% local.

> **Estado atual: Fase 3 (captura de câmera).** Já captura webcam e câmeras IP; **ainda não grava vídeo**.
> Veja [PROJECT_STATUS.md](PROJECT_STATUS.md) e a arquitetura em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Baixar e testar (Windows 11)

1. **[⬇ Baixar o instalador (Windows 11)](https://github.com/PauloEverton05/sensor-de-movimento/releases/latest/download/SentinelAI-Setup.exe)**. O link sempre baixa a versão mais recente.
2. Instale (não pede administrador). Ao aparecer o aviso do SmartScreen, clique em *Mais informações → Executar assim mesmo*.
3. Menu Iniciar → **Sentinel AI** → siga o "Como testar".

## Plataformas

| Plataforma | Situação |
|---|---|
| **Windows 11 x64** | **Única plataforma distribuída** (instalador e portátil) |
| Linux x86_64 / macOS | Só compilam e rodam os testes no CI; não são distribuídos |
| Windows 10, ARM64 | Não suportado |

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
