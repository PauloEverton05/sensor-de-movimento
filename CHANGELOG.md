# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

### Adicionado (Fase 3)
- Câmeras: cadastro de webcam local, câmera IP (RTSP) e arquivo de vídeo; credenciais RTSP
  no cofre do SO (nunca no banco nem nos logs).
- Captura por câmera com supervisor isolado, reconexão automática (backoff exponencial com
  jitter) e saúde derivada de fatos medidos (STREAMING só com frame recente).
- Inibição de sono no Windows (Power Request API, visível em `powercfg /requests`).
- Sonda de diagnóstico e `scripts/analyze_probe.py` para o teste de tela bloqueada.
- `sentinel-ctl`: discover, cameras, add-local, add-rtsp, add-file, remove, capture-start,
  capture-stop, health, snapshot.
- Migração 0002 (tipo de câmera `file`) e migrador seguro para recriação de tabelas.

### Corrigido
- `sentinel-ctl` aceita `--data-dir`/`--timeout` antes ou depois do subcomando.

## [0.1.0-alpha.1] - 2026-11-09

### Adicionado
- Fase 1: arquitetura e decisões técnicas (`docs/ARQUITETURA.md`).
- Fase 2: estrutura do projeto, máquina de estados da vigilância, esquema SQLite v1 com
  migrações, logging JSON com redação de credenciais, agente headless com instância única,
  detecção de parada não limpa, IPC local (Named Pipe / Unix socket) com autenticação por
  token, `sentinel-ctl`, empacotamento PyInstaller e CI para Windows, Linux e macOS.
