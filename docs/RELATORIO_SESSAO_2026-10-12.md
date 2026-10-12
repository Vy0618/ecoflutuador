# Relatório de alterações da sessão — EcoFlutuador V4.1

**Emissão:** 12/10/2026 às 15:40:19 (UTC−03:00)
**Fuso:** America/Sao_Paulo, UTC−03:00.
**Escopo:** alterações, revisões, reversões e verificações registradas nesta
conversa, com foco no V4.1 e nas referências V3, V4 e AquaMonitor.

Os registros disponíveis incluem atividades de 09 e 12 de outubro de 2026.
Nem todas as etapas possuem horário registrado. A ordem abaixo segue a conversa;
os horários não disponíveis não foram estimados. Datas dos arquivos e histórico
de commits não foram usados como substitutos do horário de edição.

## Alterações e resultados

| Etapa | Data disponível | Trabalho realizado | Resultado ou estado atual |
|---|---|---|---|
| 1 | Etapa inicial; horário não registrado | Leitura do V4, preparação de ambiente e dependências, incluindo OpenCV, e orientação de execução gráfica | Preparação para reconhecimento local e uso de webcam |
| 2 | Etapa inicial; horário não registrado | Ajuste do reconhecimento para garrafas e identificação da divisão da visão em três regiões | Classe `bottle` e lógica espacial adotadas como referência |
| 3 | 09/10/2026; horário não registrado | Revisão de arquivos obsoletos do V4, dependências e impacto de remoção | Relatório e inventário de organização; nenhuma exclusão do projeto foi feita nessa revisão |
| 4 | Etapa inicial; horário não registrado | Preparação inicial do V4.1 com referências do V3 e posterior substituição pelo conjunto SSD MobileNet V3 do AquaMonitor | Modelo, grafo, nomes COCO e módulos locais; caminhos relativos e registro de origem |
| 5 | Etapa inicial; horário não registrado | Implementação da linha horizontal e posterior reposicionamento, acrescentando três regiões superiores | Regiões finais: esquerda, meio, direita e baixo |
| 6 | Etapa inicial; horário não registrado | Implementação da seleção da maior caixa e classificação pelo centro; confirmação do mapeamento com o usuário | Esquerda=`a`, meio=`w`, direita=`d`, baixo ou sem alvo=`s` |
| 7 | Etapa inicial; horário não registrado | Criação do venv do V4.1, configuração em JSON e registros por inferência | Ambiente independente, validação do JSON e logs no terminal/arquivo |
| 8 | 09/10/2026 | Correção do FPS, que antes era apenas solicitado ao dispositivo | Limite de entrega de frames por software e registro dos FPS configurado/reportado; nove testes aprovados nessa etapa |
| 9 | 12/10/2026 | Inclusão de toggle `headless` no JSON e aliases `--headless`/`--no-headless`; mudança temporária para headless por padrão | Essas alterações foram desfeitas a pedido do usuário; não fazem parte da interface atual |
| 10 | 12/10/2026 | Comparação de `V3/servidorUnificado.py` com o V4.1 | Identificadas diferenças de detector, regiões, envio serial, registros e concorrência; análise sem mudança funcional nessa etapa |
| 11 | 12/10/2026 | Investigação da falta de vídeo e ajuste da abertura da janela | Vídeo por padrão, controle por `--display`/`--no-display`, posição `(40, 40)`, tamanho da câmera e processamento inicial de eventos |
| 12 | 12/10/2026 | Leitura do código e limpeza de texto residual | Removidas referências obsoletas a YOLO, tracker, cinco classes e versões anteriores; README simplificado |
| 13 | 12/10/2026 | Alteração do formato do terminal | Somente timestamp, região, objeto e quantidade; registros completos preservados em JSONL |
| 14 | 12/10/2026 | Orientação para ignorar V3, V4 e AquaMonitor no Git | Fornecidos comandos e explicada a diferença entre ignorar arquivos e retirar arquivos já versionados do índice |
| 15 | 12/10/2026 | Criação de firmware ESP32 e integração serial ao V4.1 | Envio opcional por `--serial-port`, confirmação, rampa, parada e timeout; pyserial instalado no venv |
| 16 | 12/10/2026 | Atualização da documentação para apresentação e avaliação do projeto | README da raiz, README completo do V4.1 e este relatório |

A revisão do V4 está documentada em
[ORGANIZACAO_V4.md](../../V4/docs/ORGANIZACAO_V4.md), com
[inventário por arquivo](../../V4/docs/audit/inventario-organizacao-v4.json).
Ela registrou uma simulação de limpeza com 88 testes aprovados. Essa evidência
é histórica, pertence ao V4 e não foi repetida na etapa atual de documentação.
Remoções ou alterações feitas pelo usuário no workspace foram preservadas.

## Implementação consolidada

### Reconhecimento, geometria e configuração

O V4.1 passou a executar reconhecimento local com os três arquivos do SSD
MobileNet V3 em `models/`. `models/origem.json` registra fontes e hashes do
conjunto de referência do AquaMonitor. Foram ajustados imports e caminhos para
a execução independente dos servidores das outras versões.

`config.py` resolve os caminhos em relação ao JSON e valida resolução, FPS,
confiança, intervalo, classes e parâmetros de redução e divisão da imagem.
Foram excluídas do perfil as configurações de YOLO, tracking de cruzamentos e
`nms_threshold`, que não eram usadas pelo fluxo implementado.

A geometria é compartilhada entre o desenho e a decisão. A região inferior tem
prioridade; acima dela, a largura é dividida em três. O alvo é a garrafa com
maior área de caixa, classificada pelo centro, sem exigir contenção de toda a
caixa dentro de uma região. A visualização destaca o alvo, a confiança, as
linhas, as regiões e o comando.

Os valores atuais do perfil, incluindo ajustes do usuário, são câmera 640×480
com limite de 10 FPS, entrada da rede 320×320, confiança 0,3, intervalo de
300 ms, alvo `bottle` e linha horizontal em 80% da altura. Esses ajustes do JSON
foram preservados nas correções de código.

### Correção do FPS

A câmera podia ignorar `CAP_PROP_FPS`. A captura continuava rápida e a aplicação
não limitava a entrega dos frames. `LatestFrameCamera` passou a aplicar o
intervalo `1 / fps` ao consumidor, enquanto a thread continua capturando para
manter a imagem mais recente e evitar acúmulo de vídeo atrasado.

O log de teste disponível de **09/10/2026 às 15:48:44**, horário de São Paulo,
registrou 15 FPS configurados e 30 FPS reportados pelo dispositivo. Esse horário
é de um evento de execução, não do instante exato da edição. Foram acrescentados
três testes de FPS, totalizando nove testes aprovados naquela etapa.

### Headless, reversões e vídeo

Foram acrescentadas temporariamente opções de headless no JSON e no comando.
A alteração que tornava headless o padrão foi desfeita. Posteriormente, por
solicitação explícita, foram removidas as mudanças realizadas após a correção
do FPS, antes de prosseguir com a investigação do vídeo.

A implementação atual exibe vídeo por padrão e aceita `--no-display` para
executar sem janela. `--display` solicita explicitamente a janela.
`display.enabled` foi retirado do perfil e não controla mais a exibição.
Também foram adicionados tamanho e posição explícitos da janela, uma chamada
inicial ao processamento de eventos e o campo `video_habilitado` no arquivo
completo de registros.

Nos testes dentro do ambiente isolado, a conexão ao socket da tela foi bloqueada
com `Operation not permitted`; o Qt reportou `could not connect to display :0`.
Uma execução com acesso à sessão gráfica e à webcam, fora do isolamento,
concluiu normalmente. **Não foi confirmada a causa específica da ausência de
vídeo no terminal do usuário.** O teste posterior que buscava confirmar a
visibilidade e os pixels das linhas foi interrompido e não foi tratado como
verificação concluída.

### Registros

O terminal passou de JSON completo para blocos com quatro campos:

```text
timestamp: 2026-10-12-15-30
regiao: esquerda
objeto: bottle
garrafas_detectadas: 1
```

O timestamp segue `AAAA-MM-DD-HH-SS`, sem minutos, no fuso de São Paulo. Sem alvo,
o objeto aparece como `nenhum`. Eventos sem os campos de detecção não geram
blocos vazios no terminal; erros continuam sendo informados como mensagens.

O arquivo `logs/recognition.jsonl` mantém os dados completos, timestamps ISO
8601 em UTC, sequência, eventos, comandos, confiança, caixas, centros e modo de
operação. Há rotação de 2.000.000 bytes e até três arquivos anteriores.

### Firmware e comunicação com os motores

Foi criado `firmware/ControleESP32/ControleESP32.ino`, tomando como referência
`V3/ControleESP32.ino`. Os sinais usam GPIOs 12 e 14, PWM a 50 Hz, resolução de
16 bits e pulsos de 1000–2000 µs. O alvo inicial de potência é 30% por ESC.

O acionamento segue: `a` ativa ESC 1, `w` ativa ambos, `d` ativa ESC 2 e `s`
aplica o pulso mínimo a ambos. Há armamento de três segundos, rampa não
bloqueante de 15 µs a cada 20 ms e parada por três segundos sem comandos.
Comandos inválidos também aplicam parada. O firmware usa LEDC do core
Arduino-ESP32, com caminhos para 2.x e 3.x, sem ESP32Servo.

`esp32_link.py` consulta o firmware, espera `READY`, envia a parada inicial e
confirma comandos por `CMD_OK:<comando>`. A integração envia uma decisão a cada
inferência, inclusive quando ela se repete, para renovar o timeout. O
encerramento solicita `s`; falhas de confirmação são informadas. A operação
serial depende de `--serial-port` e não é permitida no modo de imagem estática.

`pyserial` foi acrescentado a `requirements.txt` e instalado no venv. Foram
adicionados `platformio.ini`, a regra de exclusão de `.pio/` e testes de
protocolo, integração e comportamento do firmware. Para concluir a compilação,
foram instaladas as ferramentas de build que faltavam no PlatformIO local.
Nenhum upload de firmware ou teste físico de acionamento foi realizado.

## Arquivos principais da entrega

| Grupo | Arquivos |
|---|---|
| Entrada e configuração | `object-ident.py`, `config.py`, `config.json` |
| Percepção e captura | `camera.py`, `image_processing.py`, `detection/`, `models/` |
| Decisão e registros | `regions.py`, `navigation.py`, `command_log.py` |
| Comunicação | `esp32_link.py` |
| Firmware | `firmware/ControleESP32/ControleESP32.ino`, `platformio.ini` |
| Dependências e exclusões locais | `requirements.txt`, `.gitignore` do V4.1 |
| Testes | `test_camera_fps.py`, `test_navigation.py`, `test_video_display.py`, `test_esp32_link.py`, `test_firmware.py`, `firmware_behavior.cpp`, `firmware_stubs/` |
| Documentação | `README.md` da raiz e antigo `V4.1/README.md`, este relatório e documentação anterior de organização do V4 |

## Validação disponível

| Verificação | Resultado |
|---|---|
| Suíte final do V4.1 | 17 testes aprovados |
| Simulação do firmware | Comandos, rampa, parada, renovação do timeout e rollover de `millis()` aprovados nos caminhos 2.x e 3.x |
| Compilação ESP32 | Aprovada para `esp32dev`, PlatformIO Espressif32 7.0.1 e Arduino-ESP32 2.0.17 |
| Uso de memória do firmware | 21.592 bytes de RAM; 274.641 bytes de programa |
| Dependências | `pip check` aprovado; OpenCV 4.14.0.94, NumPy 2.5.3 e pyserial 3.5 no venv Python 3.12.3 |
| Formatação dos patches | `git diff --check` aprovado na validação de implementação |
| Câmera e sessão gráfica | Execução real disponível fora do sandbox; causa do problema do terminal do usuário não confirmada |
| Resposta física dos motores | Ainda não validada |

Comandos de reprodução:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -m pip check
pio run --project-dir firmware/ControleESP32 --environment esp32
```

Os testes nativos dependem de `g++`; sem ele, o teste de firmware é ignorado.
Não foram medidas precisão de detecção, velocidade dos motores ou desempenho
da embarcação. A seleção atual não mantém identidade da garrafa entre
inferências. Esses pontos permanecem como etapas de avaliação física e
experimental.

## Localização atual do projeto

O V4.1 foi promovido à raiz do repositório. Os comandos acima usam os caminhos
atuais; as descrições das etapas anteriores mantêm o nome da versão. Veja o
[registro da migração](MIGRACAO_PARA_RAIZ.md).
