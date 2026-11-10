"""Comunicação local entre interface e agente (JSON-RPC 2.0 sobre Named Pipe / Unix socket).

Este pacote não pode importar o agente nem a persistência: a interface gráfica
dependerá apenas dele (verificado pelo import-linter).
"""
