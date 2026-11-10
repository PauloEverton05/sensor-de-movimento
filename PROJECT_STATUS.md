# SENTINEL AI — Acompanhamento do Projeto

Última atualização: 2026-11-09

## Fase atual

**Fase 3 — Câmeras e captura (+ spike de tela bloqueada)**: 🟡 implementada; **aguardando os testes em hardware** descritos em [docs/TESTE-FASE-3.md](docs/TESTE-FASE-3.md), feitos pelo instalador `v0.2.0-alpha.1` (Menu Iniciar → Sentinel AI).

> **Distribuição: somente Windows 11 x64** (decisão do responsável, 2026-11-09). Linux e macOS continuam compilando e rodando os testes no CI, para não perder a portabilidade da arquitetura, mas não são publicados.

### Fase 3: critérios de conclusão

| Critério | Status |
|---|---|
| Fontes local / RTSP / arquivo | ✅ (simulado + arquivo real no CI) |
| Supervisor com isolamento de falhas, reconexão e saúde por câmera | ✅ (testes com fonte simulada) |
| Credenciais RTSP fora do banco e dos logs | ✅ (teste verifica banco, WAL e logs) |
| Inibição de sono no Windows | ✅ implementada · ⏳ efeito a validar no teste 6 |
| fps medido ≥ 95% do nominal na webcam real | ⏳ teste 2 |
| Reconexão após perda real do dispositivo | ⏳ teste 4 |
| Câmera IP real (celular) | ⏳ teste 5 |
| Captura estável por 1 h na webcam real (Windows) | ⏳ coberta pelo teste 6 (30 min) + uma rodada longa |
| **Spike de tela bloqueada (tela apagada / Modern Standby)** | ⏳ teste 6 |
| Captura na webcam real em Linux | ⏳ pendrive live (pode ser feito depois do spike) |

### Pendências registradas na Fase 3

- Enumeração de câmeras locais com **ID estável** (símbolo do Media Foundation / `/dev/v4l/by-id`). Hoje o cadastro usa o índice, e trocar webcams USB de porta pode mudar o índice.
- Inibição de sono e detecção de bloqueio em Linux/macOS (Fase 8).
- Migração de RTSP para PyAV (remux sem recodificação) na Fase 4, após verificar a licença do FFmpeg embutido.

---

**Fase 2 — Estrutura do projeto e infraestrutura**: ✅ **concluída em 2026-11-09**.

Pré-lançamento publicado: [v0.1.0-alpha.1](https://github.com/PauloEverton05/sensor-de-movimento/releases/tag/v0.1.0-alpha.1) (instalador Windows, zip portátil, Linux e macOS, este último só como build).

## Fases

| Fase | Status |
|---|---|
| 1. Arquitetura | ✅ Aprovada (2026-11-09) |
| 2. Estrutura e infraestrutura | ✅ Concluída (2026-11-09) |
| 3. Câmeras e captura (+ spike de tela bloqueada) | 🟡 Implementada; aguardando testes em hardware |
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
| D17 | Fase 3: RTSP via OpenCV (FFmpeg LGPL embutido); PyAV adiado para a Fase 4 | Evitar adotar o FFmpeg do PyAV antes de verificar a licença |
| D18 | Estado do link derivado do tempo desde o último frame, e não da thread de leitura | Driver travado dentro do `read()` não pode manter STREAMING falso |
| D19 | Inibição de sono (Windows) antecipada da Fase 8 para a 3 | Pré-requisito do spike de tela bloqueada |
| D20 | Captura diagnóstica (`capture.*`) separada da vigilância (`surveillance.*`) | Câmera capturando ≠ vídeo gravado; a vigilância só vira ACTIVE com gravação (Fase 4) |
| D21 | Cofre do SO via `keyring`; `SENTINEL_SECRET_BACKEND=memory` só para testes | Credenciais nunca no banco; o CI Linux não tem cofre |
| D22 | Distribuição somente Windows 11 x64; Linux/macOS só no CI | Decisão do responsável: testar sem ferramentas de desenvolvimento, só baixando o instalador |
| D23 | Testes guiados no próprio `sentinel-ctl` + atalhos no Menu Iniciar | O usuário final testa sem terminal nem `uv` |
| D24 | O CI instala o `setup.exe` em silêncio e roda a fumaça contra a instalação | Nenhum instalador é publicado sem ter sido instalado e executado |

## Problemas encontrados

| Data | Problema | Situação |
|---|---|---|
| 2026-11-09 | Redação de log vazava parte de senhas que contêm `@` (`rtsp://u:abc@!@host`) | ✅ Corrigido (regex gulosa até o último `@`) + teste |
| 2026-11-09 | No Windows o `python.exe` do venv é um lançador: o PID do processo filho difere do `Popen.pid` | ✅ Teste ajustado (só afeta execução pelo código-fonte) |
| 2026-11-09 | Repositório GitHub público, com produto comercial | ✅ Decisão do responsável: manter público (divulgação). Código *source-available*: proprietário, todos os direitos reservados |
| 2026-11-09 | mypy falhava só no Linux (tipo de `Client` varia por plataforma no typeshed) | ✅ Corrigido em 409a407. A release v0.1.0-alpha.1 foi gerada de c5ef571, funcionalmente idêntico |
| 2026-11-09 | Named Pipe usa o descritor de segurança padrão do Windows (proteção atual: token HMAC) | Planejado: DACL restrita ao usuário na Fase 10 |
| 2026-11-09 | `sentinel-ctl` deixou de aceitar `--data-dir` depois do subcomando (detectado pelo teste de fumaça do binário) | ✅ Corrigido + teste |
| 2026-11-09 | Recriar tabela no SQLite com `foreign_keys=ON` apagaria `camera_settings` em cascata | ✅ Migrador desliga FKs por migração e roda `foreign_key_check` antes do COMMIT + teste |

## Testes realizados

| Data | Ambiente | Suíte | Resultado |
|---|---|---|---|
| 2026-11-09 | Windows 11 Pro 26200, Python 3.12.14 (código-fonte) | unit + integration (51) | 50 ✅, 1 pulado (específico de Unix) |
| 2026-11-09 | Windows 11 Pro 26200, binário PyInstaller | integration (8) | 8 ✅ |
| 2026-11-09 | Windows 11 | ruff, ruff format, mypy --strict, lint-imports | ✅ |
| 2026-11-09 | GitHub Actions: Windows, Ubuntu, macOS arm64 | testes + build + fumaça do binário | ✅ |
| 2026-11-09 | GitHub Actions: Windows | geração do instalador Inno Setup | ✅ (instalação em máquina real ainda não testada) |
| 2026-11-09 | Windows 11 (código-fonte) | Fase 3: unit + integration (81) | 80 ✅, 1 pulado |
| 2026-11-09 | Windows 11 (binário PyInstaller com OpenCV) | integration (17) + `sentinel-ctl` | ✅ |

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
