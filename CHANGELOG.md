# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

### Adicionado
- Fase 1: arquitetura e decisões técnicas (`docs/ARQUITETURA.md`).
- Fase 2: estrutura do projeto, máquina de estados da vigilância, esquema SQLite v1 com
  migrações, logging JSON com redação de credenciais, agente headless com instância única,
  detecção de parada não limpa, IPC local (Named Pipe / Unix socket) com autenticação por
  token, `sentinel-ctl`, empacotamento PyInstaller e CI para Windows, Linux e macOS.
