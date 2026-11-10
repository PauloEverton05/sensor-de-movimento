# Fase 3: como testar no seu notebook

Roteiro para validar a captura de câmera em hardware real e executar o **teste de tela
bloqueada**, o maior risco do projeto (ARQUITETURA §12 e §20.3).

Tempo total: ~15 min para os testes 1 a 5 e ~40 min para o teste 6.

> Nesta fase o Sentinel **captura** a câmera, mas **ainda não grava vídeo** (a gravação é a Fase 4).
> As evidências do teste 6 são fotos periódicas com data e hora mais um registro por segundo.

## Preparação (uma vez)

No PowerShell, dentro da pasta do projeto:

```powershell
git pull
uv sync
```

Antes de começar:

- Feche programas que usam a câmera (Teams, Zoom, Câmera do Windows, navegador numa chamada).
- Deixe o ambiente **iluminado**. Em pouca luz a webcam reduz o fps sozinha (exposição automática), e o teste de fps falha por causa da cena, não do software.
- Ligue o notebook **na tomada**.

---

## 1. Testes automáticos (1 min)

```powershell
uv run pytest
```

Esperado: `80 passed, 1 skipped, 2 deselected` (os 2 *deselected* são os testes de hardware do passo 2). Esses testes usam câmeras simuladas e um vídeo gerado, **não** a webcam.

## 2. Webcam real (1 min, o LED acende)

```powershell
uv run pytest -m hardware -s
```

Esperado: 2 testes passando e uma linha como
`1280x720 via MSMF: 29.8 fps medido / 30.0 nominal; reconexões=0`.

Se falhar com "fps abaixo de 95%", acenda mais luzes e repita.

## 3. O agente na prática (5 min)

Use **dois terminais** na pasta do projeto.

**Terminal 1** (deixe aberto, é o agente):

```powershell
uv run sentinel-agent --console-log
```

**Terminal 2:**

```powershell
uv run sentinel-ctl discover                          # lista as webcams (o LED pisca)
uv run sentinel-ctl add-local --index 0 --name "Webcam integrada"
uv run sentinel-ctl cameras                           # confira o cadastro
uv run sentinel-ctl capture-start                     # inicia a captura
uv run sentinel-ctl health --watch                    # estado e fps a cada 2 s (Ctrl+C sai)
uv run sentinel-ctl snapshot --out foto.jpg           # salva o frame atual
uv run sentinel-ctl status                            # repare: capture_active=true, recording=false
uv run sentinel-ctl capture-stop
```

Esperado no `health --watch`: `Webcam integrada: STREAMING 30.0 fps (reconexões 0)`.

## 4. Perda de sinal e reconexão (2 min)

Com a captura ativa e o `health --watch` rodando:

1. Abra **Configurações → Privacidade e segurança → Câmera** e **desligue** "Acesso à câmera".
2. Em até ~5 s o estado deve mudar para **`NO_SIGNAL`**. O agente nunca deve continuar mostrando `STREAMING`.
3. **Religue** o acesso. Em até ~1 min (o intervalo entre tentativas cresce) deve voltar para **`STREAMING`**, com `reconexões 1` ou mais.

## 5. Câmera IP usando o celular (opcional, 5 min)

1. No Android, instale o app gratuito **IP Webcam** e toque em **Iniciar servidor**.
   O app mostra um endereço como `http://192.168.0.15:8080`.
2. O celular e o notebook precisam estar **no mesmo Wi-Fi**.
3. Cadastre a câmera, trocando o IP pelo seu:

```powershell
uv run sentinel-ctl add-rtsp --name "Celular" --url rtsp://192.168.0.15:8080/h264_ulaw.sdp
```

   Se o app estiver configurado com usuário e senha, acrescente `--user nome`. A senha é pedida no terminal e guardada no **Gerenciador de Credenciais do Windows**, nunca no banco.
4. Rode `capture-start` e `health --watch`: as duas câmeras devem aparecer em `STREAMING`.
5. Desligue o Wi-Fi do celular. O celular deve ir para `NO_SIGNAL` **sem afetar a webcam**. Religue e confira que ele volta sozinho.

---

## 6. Teste de tela bloqueada (o principal, ~40 min)

Seu Vivobook usa **Modern Standby**: quando a tela apaga, o Windows pode suspender os
programas. Este teste descobre se o Sentinel continua capturando nessa situação.

### 6.1 Montagem

- Notebook **na tomada**, com o agente rodando no Terminal 1 (passo 3) e só a webcam habilitada (se cadastrou o celular, remova com `uv run sentinel-ctl remove <id>`).
- Coloque **o celular com um cronômetro rodando** na frente da webcam. Ele é a prova visual de continuidade.

### 6.2 Execução

```powershell
uv run sentinel-ctl capture-start --probe
```

(Opcional) Num **PowerShell como Administrador**, confirme que o Sentinel está segurando o sono:

```powershell
powercfg /requests
```

Deve aparecer `Sentinel AI: vigilância ativa` nas seções **SYSTEM** e **EXECUTION**.

Então:

1. Anote o horário e pressione **Win + L**.
2. **Não toque no notebook por 30 minutos.** A tela vai apagar sozinha depois de ~1 minuto, e é exatamente esse o cenário que queremos testar.
3. Passe na frente da câmera três vezes, aproximadamente aos 3, 9 e 14 minutos, e **anote os horários**.
4. Depois dos 30 minutos, desbloqueie e rode:

```powershell
uv run sentinel-ctl capture-stop
uv run python scripts/analyze_probe.py --latest
```

### 6.3 Como ler o resultado

O analisador imprime um relatório e o veredito **`PASSOU`** ou **`FALHOU`**:

| Campo | O que significa |
|---|---|
| `longest_locked_min` | Maior trecho contínuo com a sessão bloqueada (precisa ser ≥ 15) |
| `agent_suspended_gaps` | Momentos em que **o processo inteiro** parou. Se tiver itens, o Windows suspendeu o agente (Modern Standby) |
| `fps_locked` × `fps_unlocked` | O fps com a tela bloqueada precisa ser ≥ 95% do normal |
| `gaps_over_2s` | Lacunas de frames da câmera, mesmo com o agente rodando |

Confira também as fotos, que ficam em
`%LOCALAPPDATA%\SentinelAI\diagnostics\probe-<data>\snapshots\`.
São uma a cada 10 s, com a data e a hora gravadas no canto. Compare com o cronômetro
filmado e confira se você aparece nos horários anotados.

(Opcional, PowerShell como Administrador) `powercfg /sleepstudy` gera um relatório em HTML
mostrando se o notebook entrou em Modern Standby durante o teste.

### 6.4 Teste de controle (opcional, recomendado)

Repita o teste 6 com **inibição de sono desligada**, para provar que é ela que mantém a captura:

```powershell
uv run sentinel-ctl capture-start --probe --allow-sleep
```

O esperado é **FALHAR**, com `agent_suspended_gaps` preenchido. Se passar mesmo assim, ótimo:
o seu notebook não suspende programas com a tela bloqueada.

### 6.5 Se o teste principal falhar

Rode a variante com a tela sempre ligada (a tela fica ligada, mas bloqueada):

```powershell
uv run sentinel-ctl capture-start --probe --keep-display-on
```

---

## O que me enviar

Só texto. **Não precisa enviar as fotos.**

1. A saída do `scripts/analyze_probe.py --latest` de cada variante que rodou (6.2, 6.4, 6.5).
2. A linha de fps do teste 2.
3. O que aconteceu nos testes 4 e 5.
4. Qualquer mensagem de erro do Terminal 1.

Com isso, a matriz de compatibilidade é preenchida e a estratégia da seção 12.1 é confirmada
ou revista antes da Fase 4.
