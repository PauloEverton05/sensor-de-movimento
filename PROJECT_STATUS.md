# SENTINEL AI — Acompanhamento do Projeto

Última atualização: 2026-11-09

## Fase atual

**Fase 2 — Estrutura do projeto e infraestrutura**: ✅ **concluída em 2026-11-09**. Próxima: Fase 3 (câmeras e captura + spike de tela bloqueada).

Pré-lançamento publicado: [v0.1.0-alpha.1](https://github.com/PauloEverton05/sensor-de-movimento/releases/tag/v0.1.0-alpha.1) (instalador Windows, zip portátil, Linux e macOS, este último só como build).

## Fases

| Fase | Status |
|---|---|
| 1. Arquitetura | ✅ Aprovada (2026-11-09) |
| 2. Estrutura e infraestrutura | ✅ Concluída (2026-11-09) |
| 3. Câmeras e captura (+ spike de tela bloqueada) | Não iniciada |
| 4. Gravação contínua e segmentação | Não iniciada |
| 5. Detecção de movimento | Não iniciada |
| 6. IA e detecção de pessoas | Não iniciada |
| 7. Catálogo de pessoas e eventos | Não iniciada |
| 8. Serviço de segundo plano | Não iniciada |
| 9. Interface gráfica | Não iniciada |
| 10. Segurança, recuperação e otimização | Não iniciada |
| 11. Compatibilidade multiplataforma | Não iniciada |
| 12. Instaladores e distribuição | Não iniciada |

### Fase 2: critérios de conclusão

| Critério | Status |
|---|---|
| Projeto `uv` + ruff + mypy (strict) + import-linter | ✅ |
| Logging JSON com redação de credenciais | ✅ |
| Configuração de bootstrap (`agent.toml`) | ✅ |
| Esquema SQLite v1 + migrações transacionais | ✅ |
| Esqueleto IPC (hello/ping/status/shutdown) com autenticação | ✅ |
| Agente com instância única e detecção de parada não limpa | ✅ |
| Agente empacotado (PyInstaller) responde a `status` — Windows 11 | ✅ local |
| Agente empacotado responde a `status` — Linux / macOS | ✅ CI |
| CI verde nos 3 SOs | ✅ (run 42725329497) |

## Funcionalidades concluídas

- Máquina de estados da vigilância (6 estados obrigatórios + transições validadas) e separação `desired_state` × `observed_state` no domínio.
- Esquema v1: câmeras, configurações, retenção, sessões, gravações, segmentos, pessoas, consentimentos, referências, eventos, detecções, revisões, histórico operacional e estado do agente. Inclui integridade referencial, CHECKs e índices.
- Agente headless (`sentinel-agent`) e CLI (`sentinel-ctl status|ping|shutdown`).

## Funcionalidades pendentes

- Tudo a partir da Fase 3.

## Decisões arquiteturais

| # | Decisão | Motivo principal |
|---|---|---|
| D1 | Python 3.12 + PySide6 + PyAV/FFmpeg LGPL + OpenCV + ONNX Runtime + SQLite | Melhor suporte a câmera e IA multiplataforma com uma única linguagem |
| D2 | Agente headless separado da interface; inferência em processo próprio | A gravação nunca depende da interface nem da IA |
| D3 | JSON-RPC sobre Named Pipe / Unix socket, sem TCP | Nada exposto na rede |
| D4 | Agente na sessão do usuário (não serviço) para webcam | Session 0, TCC e privacidade de câmera |
| D5 | fMP4 segmentado | Arquivo legível mesmo após queda |
| D6 | H.264 via encoder do SO/HW; sem libx264 | Licença GPL e patentes |
| D7 | YOLOX (Apache-2.0), não Ultralytics (AGPL) | Licenciamento comercial |
| D8 | YuNet + SFace, não InsightFace | Pesos InsightFace não comerciais |
| D9 | `desired_state` × `observed_state` persistidos | Interface nunca mostra estado falso |
| D10 | Produto comercial e fechado; macOS 13+; reconhecimento facial na 1.0 | Decisão do responsável (2026-11-09) |
| D11 | Sem certificado de assinatura por enquanto: Nuitka, autoassinado estável no macOS, reavaliar antes da venda | Sem orçamento (ARQUITETURA §20.1) |
| D12 | Spike de tela bloqueada antecipado para o fim da Fase 3 | Maior risco do projeto; o notebook de teste tem Modern Standby |
| D13 | macOS, Windows 10 e ARM64 = "não suportado" até haver hardware | Regra: não declarar suporte sem teste real; todos os notebooks são Windows 11 |
| D14 | Pacote único `src/sentinel` em vez de workspace multi-pacote | Evitar camada sem ganho; fronteiras via import-linter |
| D15 | IPC sobre `multiprocessing.connection` (stdlib) | Framing + HMAC mútuo nos 3 SOs sem dependência extra |
| D16 | Token/lock/socket em diretório de execução privado, separado dos dados | Dados podem estar em disco externo com ACL ampla |

## Problemas encontrados

| Data | Problema | Situação |
|---|---|---|
| 2026-11-09 | Redação de log vazava parte de senhas que contêm `@` (`rtsp://u:abc@!@host`) | ✅ Corrigido (regex gulosa até o último `@`) + teste |
| 2026-11-09 | No Windows o `python.exe` do venv é um lançador: o PID do processo filho difere do `Popen.pid` | ✅ Teste ajustado (só afeta execução pelo código-fonte) |
| 2026-11-09 | Repositório GitHub público, com produto comercial | ✅ Decisão do responsável: manter público (divulgação). Código *source-available*: proprietário, todos os direitos reservados |
| 2026-11-09 | mypy falhava só no Linux (tipo de `Client` varia por plataforma no typeshed) | ✅ Corrigido em 409a407. A release v0.1.0-alpha.1 foi gerada de c5ef571, funcionalmente idêntico |
| 2026-11-09 | Named Pipe usa o descritor de segurança padrão do Windows (proteção atual: token HMAC) | Planejado: DACL restrita ao usuário na Fase 10 |

## Testes realizados

| Data | Ambiente | Suíte | Resultado |
|---|---|---|---|
| 2026-11-09 | Windows 11 Pro 26200, Python 3.12.14 (código-fonte) | unit + integration (51) | 50 ✅, 1 pulado (específico de Unix) |
| 2026-11-09 | Windows 11 Pro 26200, binário PyInstaller | integration (8) | 8 ✅ |
| 2026-11-09 | Windows 11 | ruff, ruff format, mypy --strict, lint-imports | ✅ |
| 2026-11-09 | GitHub Actions: Windows, Ubuntu, macOS arm64 | testes + build + fumaça do binário | ✅ |
| 2026-11-09 | GitHub Actions: Windows | geração do instalador Inno Setup | ✅ (instalação em máquina real ainda não testada) |

## Hardware de teste

- ASUS Vivobook Go E1504FA · Ryzen 5 7520U + Radeon · webcam USB2.0 HD UVC integrada · **Modern Standby** · Windows 11 Pro 26200
- Outros notebooks: todos Windows 11
- Linux: mesmo notebook via pendrive live/dual boot
- Câmera IP: celular Android como RTSP + mediamtx

## Matriz de compatibilidade validada

| Plataforma | Build | Instalação | Webcam | Câmera IP | Bloqueio (tela ligada) | Bloqueio (tela apagada) | Reinício | 24 h | Consumo |
|---|---|---|---|---|---|---|---|---|---|
| Windows 11 x64 | ✅ (agente Fase 2) | — | — | — | — | — | — | — | — |
| Ubuntu x64 | ✅ CI (agente Fase 2); hardware ⏳ | — | — | — | — | — | — | — | — |
| macOS arm64 | ✅ CI (só build) | ❌ não suportado | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Windows 10 | ❌ não suportado (sem hardware) | | | | | | | | |
| ARM64 (Win/Linux) | ❌ não suportado (sem hardware) | | | | | | | | |

Legenda: ✅ validado em hardware · ⚠️ funciona com limitação documentada · ❌ não suportado · ⏳ pendente · — não testado
