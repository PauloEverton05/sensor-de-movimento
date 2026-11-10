SENTINEL AI - COMO TESTAR (Windows 11)
======================================

Esta versão CAPTURA a webcam, mas AINDA NÃO GRAVA VÍDEO (a gravação vem na próxima fase).
O objetivo destes testes é descobrir se o Sentinel continua vendo a câmera com a tela
BLOQUEADA, que é o maior risco do projeto.

Tempo total: cerca de 45 minutos (quase todo ele sem mexer no notebook).


ANTES DE COMEÇAR
----------------
- Notebook NA TOMADA.
- Ambiente ILUMINADO (no escuro a webcam reduz o fps sozinha e o teste falha à toa).
- Feche Teams, Zoom, Câmera do Windows e qualquer chamada no navegador.


INSTALAÇÃO
----------
1. Baixe "SentinelAI-...-windows11-x64-setup.exe" na página de Releases do GitHub.
2. Abra o arquivo. O Windows vai mostrar "O Windows protegeu o computador", porque o
   programa ainda não tem assinatura digital. Clique em "Mais informações" e depois em
   "Executar assim mesmo".
3. Avance até o fim. Não precisa ser administrador.

Tudo fica no Menu Iniciar, na pasta "Sentinel AI".


TESTE 1 - Webcam (1 minuto)
---------------------------
Menu Iniciar > Sentinel AI > "1 - Teste da webcam (1 minuto)"

- Uma segunda janela, "Agente", abre sozinha. NÃO a feche durante o teste.
- O LED da câmera acende e o teste mede o fps por 60 segundos.
- No fim aparece PASSOU ou FALHOU, com uma linha parecida com:
      1280x720 via MSMF
        29.8 fps medido / 30.0 nominal; reconexões: 0
- Se falhar por fps baixo, acenda mais luzes e repita.


TESTE 2 - Tela bloqueada (o principal, ~35 minutos)
----------------------------------------------------
Menu Iniciar > Sentinel AI > "2 - Teste de tela bloqueada"

1. Coloque o CELULAR COM UM CRONÔMETRO rodando na frente da webcam.
2. Quando a janela disser que a captura está rodando, pressione  Win + L.
3. NÃO toque no notebook por 30 minutos. A tela vai apagar sozinha depois de ~1 minuto:
   é exatamente isso que queremos testar.
4. Passe na frente da câmera por volta dos minutos 3, 9 e 14 e anote os horários.
5. Desbloqueie, volte para a janela do teste e pressione ENTER.

O resultado aparece na tela:
      RESULTADO: PASSOU   (ou FALHOU)
      Maior bloqueio contínuo ... 30.2 min
      Agente suspenso ........... não
      Webcam integrada: 29.9 fps desbloqueado / 29.8 fps bloqueado (100%); lacunas: 0

O que cada linha quer dizer:
- "Agente suspenso": se aparecer um horário aqui, o Windows CONGELOU o programa enquanto a
  tela estava apagada (Modern Standby).
- "lacunas": períodos de 2 segundos ou mais sem imagem da câmera.
- "bloqueado (xx%)": o fps com a tela bloqueada precisa ficar em pelo menos 95% do normal.

As fotos do teste (uma a cada 10 s, com data e hora gravadas no canto) ficam em:
      Menu Iniciar > Sentinel AI > "Pasta de resultados dos testes"
Abra algumas e compare com o cronômetro filmado. Confira se você aparece nos horários
que anotou.


TESTE 3 - Controle (opcional, recomendado, ~35 minutos)
-------------------------------------------------------
Menu Iniciar > Sentinel AI > "3 - Teste de controle (sem inibir o sono)"

É o mesmo teste, só que o Sentinel NÃO impede o Windows de dormir. Ele serve para provar
que é a inibição de sono que mantém a câmera viva. O esperado é FALHAR, com "Agente
suspenso" preenchido. Se passar mesmo assim, ótimo: o seu notebook não congela programas
com a tela bloqueada.


O QUE ME ENVIAR
---------------
Só texto. NÃO precisa enviar as fotos.

1. O texto do resultado de cada teste (copie da janela).
   Para copiar: selecione com o mouse e pressione Enter. Ou pegue o arquivo "report.json"
   que fica dentro da pasta do teste, em "Pasta de resultados dos testes".
2. Qualquer mensagem de ERRO que tenha aparecido, inclusive na janela "Agente".


SE ALGO DER ERRADO
------------------
- "a webcam não começou a enviar imagens": feche outros programas de câmera e confira
  Configurações > Privacidade e segurança > Câmera > "Acesso à câmera" (ligado) e
  "Permitir que aplicativos da área de trabalho acessem a câmera" (ligado).
- "já existe uma captura em andamento": abra "Prompt do Sentinel AI" e digite
      sentinel-ctl capture-stop
- Para fechar o agente: feche a janela "Agente", ou no Prompt do Sentinel AI digite
      sentinel-ctl shutdown


COMANDOS AVANÇADOS (opcional)
-----------------------------
No "Prompt do Sentinel AI":
      sentinel-ctl status                   estado do agente
      sentinel-ctl cameras                  câmeras cadastradas
      sentinel-ctl capture-start            inicia a captura
      sentinel-ctl health --watch           fps e estado a cada 2 s (Ctrl+C sai)
      sentinel-ctl snapshot --out foto.jpg  salva o frame atual
      sentinel-ctl capture-stop             para a captura
      sentinel-ctl analyze                  reanalisa o último teste
      sentinel-ctl add-rtsp --url rtsp://IP:8080/h264_ulaw.sdp --name Celular
                                            câmera IP (ex.: app Android "IP Webcam")

Perda de sinal: com "health --watch" rodando, desligue o acesso à câmera em
Configurações > Privacidade > Câmera. O estado deve virar NO_SIGNAL em até ~5 s e voltar
para STREAMING sozinho quando você religar.
