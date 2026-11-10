# Licenças de terceiros

Este arquivo é item obrigatório de release (docs/ARQUITETURA.md §20). Toda dependência
distribuída com o produto deve constar aqui **antes** de ser adicionada.

Regra: nenhuma dependência GPL/AGPL ou com pesos/modelos de uso não comercial.

## Dependências distribuídas (runtime)

| Componente | Versão mínima | Licença | Uso |
|---|---|---|---|
| CPython | 3.12 | PSF-2.0 | Runtime |
| platformdirs | 4.2 | MIT | Diretórios padrão por SO |
| pydantic / pydantic-core | 2.7 | MIT | Validação de configuração e mensagens IPC |
| SQLite (via CPython) | 3.x | Domínio público | Banco de dados |

## Ferramentas de build e desenvolvimento (não distribuídas)

| Componente | Licença | Observação |
|---|---|---|
| PyInstaller | GPL-2.0 **com exceção de bootloader** | A exceção permite distribuir executáveis gerados sob qualquer licença |
| pytest | MIT | |
| ruff | MIT | |
| mypy | MIT | |
| import-linter | BSD-2-Clause | |
| hatchling | MIT | |

## Previstas para as próximas fases (a confirmar na adoção)

| Componente | Licença | Restrição |
|---|---|---|
| FFmpeg (build próprio) | LGPL-2.1+ | Compilar **sem** `--enable-gpl`/`--enable-nonfree`; publicar as flags de configuração |
| PyAV | BSD-3-Clause | |
| OpenCV | Apache-2.0 | |
| ONNX Runtime | MIT | |
| PySide6 / Qt 6 | LGPL-3.0 | Link dinâmico; permitir a substituição das bibliotecas Qt |
| YOLOX (modelos) | Apache-2.0 | |
| ByteTrack | MIT | |
| YuNet / SFace (OpenCV Zoo) | MIT / Apache-2.0 | |
