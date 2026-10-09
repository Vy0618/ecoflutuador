# Roteiro de implementação do ciclo autônomo V4.5

Este documento orienta as próximas implementações. Os comandos do simulador
V4.5 descritos abaixo são a interface a construir; ainda não estão disponíveis.
O verificador de referência V4 e a suíte atual V4.5 já podem ser executados.

## Objetivo e escopo

Incorporar somente:

1. Ativação do reconhecimento pelo HC-SR04, janela de execução, timeouts e rearme.
2. Confirmação de direção em três frames, histerese e tolerância breve à perda.
3. Arquivo YAML único de configuração da aplicação e simulação por terminal.

Manter os módulos e a interface atuais. Não incorporar fauna, GPS, sensores da
água, sensor da rede, telemetria remota, banco de dados ou um novo dashboard.
Não substituir o MobileNet nesta tarefa. Simulação deve ser explícita, sem
fallback automático quando o modelo real falhar. Preservar V3 e V4.

## 1. Fluxo encontrado na V4

```text
HC-SR04 → ESP32: leitura, filtro, calibração relativa e confirmação
        → EVENT:START:0/1 + TEL periódico
        → UART → SerialLink → fila com instante de recebimento
        → RecognitionController
        → câmera → detector → DecisionEngine → a/w/d/s → ESP32
```

O sensor usa TRIG33/ECHO32 na ESP32; ECHO requer condicionamento externo para
3,3 V. A V4 usa UART2 RX16/TX17 a 115200 baud para a Raspberry, configurada em
`/dev/serial0`. O firmware também espelha TEL em USB. A V4.5 usa USB serial hoje:
preservar esse transporte inicialmente e emitir os eventos/TEL nele, sem exigir
migração para GPIO UART para implementar o gatilho.

Amostragem ultrassônica: 100 ms, pulseIn limitado a 25 ms, mediana de cinco
amostras, baseline inicial de 30 medianas, ativação com diferença de 15 cm e
liberação com 10 cm, três confirmações de presença e cinco de liberação.
São parâmetros provisórios de bancada, não calibração física comprovada.
Essa confirmação do sensor é diferente dos três frames da navegação.

No Pi, START sobe: WAITING → CONFIRMING (0,1 s) → RECOGNIZING.
Detecções levam a TRACKING. START desce, ausência de detecção por 2 s ou janela
de 15 s expirada: STOP e WAITING. Sensor inválido, serial/TEL vencida ou falha:
STOP e FAULT. Recuperação exige liberação e nova borda, sem retomar movimento.

A captura continua em WAITING; a inferência fica suspensa. Não há desligamento
da Raspberry ou confirmação de coleta física. O fim da janela significa fim
da tentativa, não prova de que o lixo entrou no barco.

A decisão da V4 usa maior alvo, três confirmações de direção, histerese de 4%
da largura e perda tolerada por 0,5 s. Ela também contém classes/fauna fora do
escopo e uma falha a evitar: qualquer classe detectada renova o timeout do ciclo,
mesmo quando a política ignora essa classe. Na V4.5, somente alvo válido renova.

## 2. Contrato do comportamento a implementar

Separar modo do operador e estado do ciclo:

- MANUAL: operador controla; eventos do sensor não iniciam coleta.
- AUTO: operador arma a automação; começa em STANDBY, com motores parados.
- CONFIRMING: START válido permanece alto durante 0,1 s.
- RECOGNIZING: inferência ativa, ainda aguardando alvo.
- TRACKING: alvo válido observado; navegação decide comandos.
- FAULT: falha identificada, STOP solicitado e ciclo inibido.

Entrar em AUTO não inicia movimento. Sair de AUTO invalida resultados em andamento
e envia STOP. Expirar uma tentativa mantém AUTO armado em STANDBY, mas não permite
reinício enquanto START continuar alto. Reiniciar a sessão serial ou o processo
com START alto também exige observar nível baixo antes de aceitar nova subida.

Inicialmente, START:0 durante uma tentativa interrompe o ciclo, seguindo a V4.
Essa escolha precisa ser validada fisicamente: sair do campo do ultrassônico
não comprova coleta. Não inventar confirmação de coleta nessa etapa.

| Prazo | Valor inicial | Efeito |
|---|---:|---|
| Acomodação do START | 0,1 s | Passar da confirmação ao reconhecimento. |
| Perda visual breve | 0,5 s | STOP se não houver novo alvo válido. |
| Ausência prolongada de alvo | 2 s | Encerrar tentativa e voltar a STANDBY. |
| Janela total | 15 s | Encerrar mesmo com detecções contínuas. |
| Telemetria sem atualização | 3 s | FAULT e STOP; START isolado não renova validade do sensor. |
| Câmera sem novo frame | 1 s durante ciclo | FAULT e STOP. |
| Idade máxima de captura | 0,5 s | Descartar resultado antigo. |
| Orçamento de inferência | 300 ms | Rejeitar resultado atrasado; sem alegar interromper chamada travada. |

Usar relógio monotônico e verificar vencimentos também quando não chegam frames
ou mensagens. Reiniciar candidato, contador, último alvo e histerese ao encerrar
uma tentativa. O maior alvo é escolhido entre `bottle` acima do limiar de confiança.

Três frames devem ser distintos, recentes e consecutivos confirmando a mesma
direção candidata. Frame repetido não conta; frame sem alvo quebra confirmação.
Ao trocar de direção, manter o comando confirmado anterior até confirmar a nova.
Durante os primeiros três frames, manter STOP. STOP por falha ou expiração
não passa por confirmação nem histerese.

## 3. Ordem de trabalho e entregáveis

### Etapa A — Configuração central

Adaptar `config.py`, criar `v4.5/config.yaml` e aceitar `--config` em `servidor.py`.
O arquivo padrão é resolvido pela localização do programa; caminhos do modelo
são relativos ao YAML, independentemente do diretório de execução.

Seções necessárias: `serial`, `camera`, `model`, `recognition`, `decision`, `web`.
Configurar porta, baud, timeouts/reconexão; backend/índice/resolução/FPS/buffer/JPEG;
paths individuais de pesos, grafo e classes; tamanho de entrada/confiança/NMS;
três zonas, confirmação/histerese/perda; todos os prazos do ciclo; host/porta HTTP.

Adicionar `config.example.yaml` sem caminhos pessoais. Manter `config.local.yaml`
ignorado pelo Git, escolhido explicitamente por `--config`; não fazer merge implícito.
Variáveis de ambiente existentes podem sobrescrever o YAML com precedência documentada.

Validar tipos, números finitos, limites de confiança, dimensões positivas,
quantidade inteira de frames, histerese entre 0 e 1/3 e relações entre prazos.
Validar arquivos do modelo ao ativar o detector real; a simulação não exige pesos.

O YAML configura software da Raspberry. Pinos, mediana e calibração executados
na ESP32 ficam em um header de configuração do firmware documentado; mudar o
YAML não reprograma a ESP32. Não criar transmissão remota de configuração nesta
etapa. Uma futura geração de header a partir de YAML pode unificar o build.

Conclusão: a mesma configuração é consumida pelos componentes e pelo simulador;
alterar o diretório de execução não muda os paths. Tests cobrem YAML inválido.

### Etapa B — Protocolo e simulador, antes da integração física

Extrair o framing/parser de `serial_manager.py` para um módulo independente.
Suportar CMD_OK/PWR_OK existentes, `EVENT:START:0/1`, `TEL:{...}`, boot e erro.
Validar tipos/validade do bloco ultrassônico. Rejeitar NaN, linhas excessivas,
fragmentos incompletos e mensagens velhas; registrar erro sem ativar coleta.
Mensagem inválida não renova freshness. Atualizar nível START também por TEL.

Usar callback que coloca eventos numa fila limitada; somente o coordenador
consome e altera o estado. Associar timestamp de recebimento e sessão serial.
Não carregar modelo nem executar navegação dentro da thread leitora.

Criar `simulation.py`: entrada JSONL por stdin/arquivo, relógio virtual, câmera e
detector sintéticos, transporte em memória. Reusar exatamente parser, estados,
navegador e controlador da produção. O modo simulado jamais abre dispositivos
ou carrega o MobileNet; UART falsa recebe os mesmos bytes que UART real.

Conclusão: stdin pode injetar linhas serial fragmentadas e observar comandos
de saída; mensagens não dependem de tempo real, sockets ou hardware.

### Etapa C — Ciclo acionado pelo sensor

Adicionar `recognition.py` independente de Flask/OpenCV. Integrar ao controlador.
Manter um tick periódico independente da captura, pois a câmera atual chama
processamento na própria thread e deixa de avançar quando a leitura trava.
Serial e captura publicam eventos; o coordenador serializa decisões. Inferência
em andamento carrega identificação da tentativa e timestamp para descartar
resultados após STOP, troca de modo, expiração ou reconexão.

Em STANDBY não chamar detector. Carregar pesos uma vez ao armar AUTO e manter
o modelo em memória: o standby desta etapa suspende inferência, não o Pi inteiro.
Preservar streaming manual. No automático, deixar streaming condicionado a
um cliente conectado para evitar codificação JPEG sem observador; não exigir
economia de energia comprovada sem medição física.

Conclusão: todos os estados/prazos/rearme descritos funcionam pelo simulador;
falhas solicitam STOP, e frames de uma tentativa anterior não movem o barco.

### Etapa D — Decisão temporal

Evoluir `navigator.py` para objeto com estado, mantendo a função de zonas como
base. Implementar três frames, histerese de 4% e tolerância de perda de 0,5 s.
Representar detecção com bbox xywh, classe, confiança, frame_id e captured_at.
Separar a anotação da imagem da decisão; não duplicar inferência.

Conclusão: centro da imagem confirma avanço no terceiro frame; pequenos
deslocamentos na fronteira não alternam comando; perda breve preserva movimento;
perda vencida para. Esses testes também executam com larguras 320 e 640.

### Etapa E — Firmware mínimo de ultrassônico

Adaptar somente firmware em `v4.5`, preservando pinos/mapeamento dos motores.
Reaproveitar e testar isoladamente o algoritmo ultrassônico da V4; excluir rede,
GPS, sensores ambientais e suas dependências. Emitir EVENT/TEL na USB atual.
Leitura limitada e rampa não bloqueante são necessárias para servir sensor e
protocolo continuamente; a rampa atual usa while/delay e atrasa ambos.

Configurar PWM desligado no build de testes; STOP deve atualizar alvo e PWM
imediatamente. Preparar testes C++ nativos do algoritmo. Timeout da tentativa
no Pi não protege o motor se o cabo cair. Para validação física posterior,
incluir o lease/heartbeat mínimo da V4 e testá-lo separadamente, sem importar
os demais sensores. Esse é requisito de proteção do controle, não um novo produto.

Conclusão: lógica do sensor passa em C++ nativo e firmware compila para placa
especificada quando toolchain disponível. Não fazer upload/acionamento automático.
Compilação alvo, elétrica e calibração permanecem pendências quando não acessíveis.

### Etapa F — Regressão e documentação

Manter rotas, modo manual e arquivos da interface. Mostrar separadamente AUTO
armado e estado do ciclo. Registrar motivo do STOP, sensor atual, idade TEL,
contagem de confirmação e tempo restante via log/estado, sem novo dashboard.
Executar suite existente e cenários novos num único comando, com código de saída
não zero em falha. Atualizar README e registro de progresso após cada etapa.

## 4. Contrato do terminal a construir

Interface proposta, ainda não implementada:

```bash
python "v4.5/Servidor 1.0/servidor.py" simulate --config v4.5/config.yaml
python "v4.5/Servidor 1.0/servidor.py" simulate --scenario v4.5/tests/scenarios/coleta.jsonl
python "v4.5/Servidor 1.0/servidor.py" simulate --all-scenarios
```

Cada linha do stdin será um comando JSON. Exemplos:

```json
{"op":"mode","value":"auto"}
{"op":"rx","line":"TEL:{\"schema\":1,\"ultrasonic\":{\"enabled\":true,\"valid\":true,\"calibrated\":true,\"start_detected\":false}}"}
{"op":"rx","line":"EVENT:START:1"}
{"op":"advance","seconds":0.1}
{"op":"frame","frame_id":1,"width":320,"height":240,"detections":[{"class":"bottle","confidence":0.9,"bbox":[20,60,30,60]}]}
{"op":"frame","frame_id":2,"width":320,"height":240,"detections":[{"class":"bottle","confidence":0.9,"bbox":[20,60,30,60]}]}
{"op":"frame","frame_id":3,"width":320,"height":240,"detections":[{"class":"bottle","confidence":0.9,"bbox":[20,60,30,60]}]}
{"op":"assert","state":"TRACKING","command":"a","detector_calls":3}
{"op":"rx","line":"EVENT:START:0"}
{"op":"assert","state":"STANDBY","command":"s"}
```

`frame` entrega um novo frame à câmera falsa; o detector falso devolve os resultados
associados somente quando chamado pelo controlador. Frame em STANDBY não incrementa
`detector_calls`. Detecções injetadas têm o mesmo contrato do detector real.

Outras operações: `rx_chunk` com fragmento contendo ou não newline; `disconnect`;
`reconnect`; `detector_error`; `inference_delay`; `camera_stall`; `status`; `quit`.
`advance` percorre os prazos na ordem em que vencem, sem sleep. Atualização de TEL
não é automática: cenários longos devem fornecer explicitamente telemetria válida
ou configurar uma fonte periódica declarada. Camera_stall não equivale a frame vazio.

Saída JSONL: relógio, entrada, estado, última direção, motivo, comandos serial
emitidos, detector_calls e freshness. `assert` produz erro e exit code não zero
em divergência. Logs humanos ficam em stderr para preservar JSONL de stdout.

## 5. Cenários automatizados obrigatórios

| Cenário | Verificação |
|---|---|
| Standby/manual | Zero inferências e nenhum movimento provocado pelo sensor. |
| START válido | Confirmar e iniciar inferência; não mover antes de três frames. |
| START falso durante confirmação | Cancelar início; permanecer parado. |
| Alvo esquerda/centro/direita | a/w/d somente após terceiro frame distinto. |
| Frame repetido/velho | Não confirmar direção nem renovar alvo. |
| Classe ignorada/confiança baixa | Não renovar timeout de alvo válido. |
| Histerese | Oscilação dentro da margem mantém direção; fora exige confirmação. |
| Perda inferior/superior a 0,5 s | Manter temporariamente; depois STOP. |
| Sem alvo por 2 s | Voltar a STANDBY mesmo recebendo frames vazios. |
| Janela de 15 s | Encerrar mesmo com alvos e TEL continuamente válidos. |
| START alto após encerramento | Não rearmar até receber baixo e nova subida. |
| TEL ausente/vencida/inválida | Não usar dado velho para iniciar ou continuar. |
| Serial cai/reconecta/ESP reinicia | STOP, invalidar ciclo e exigir fresh START. |
| Câmera trava | Timeout tratado mesmo sem callback de captura. |
| Resultado chega após prazo/troca de modo | Descartar; nenhum novo movimento. |
| Detector falha | STOP e FAULT; nunca substituir por mock. |
| JSON/linha fragmentada ou longa | Parser consistente, sem ativação espúria. |
| Sair do programa | Registrar tentativa de STOP e liberar recursos. |
| YAML inválido/cwd diferente | Erro explícito ou paths estáveis. |

Executar cenários ao término de cada etapa. Manter relógio injetável para evitar
testes de 15 segundos e dependência de agendamento das threads.

## 6. Verificações já disponíveis

Com o ambiente virtual e dependências instalados, na raiz:

```bash
python -m unittest discover -s "v4.5/Servidor 1.0/tests" -v
python v4.5/tools/verificar_referencia_v4.py
```

Baseline V4.5: 17 testes passaram em Python 3.12 no ambiente isolado existente.
O segundo comando injeta linhas EVENT/TEL, resultados de detector e tempo virtual
na V4 existente. Verifica START, três frames, perda breve/STOP, timeout sem alvo,
rearme, sensor inválido, histerese e janela máxima. Não inicia `Pipeline.setup()`.
Não abre hardware, modelo real ou API. Seu propósito é validar a referência antes
de portar as regras; não prova que elas já existem na V4.5.

## 7. Como executar este roteiro em desenvolvimento

Seguir A → B → C → D → E → F. A cada etapa: implementar, rodar regressões,
registrar arquivos alterados/evidências/pendências e avançar no trabalho local
autorizado. Não pedir confirmação para decisões rotineiras previstas aqui.
Não instalar serviços, modificar V3/V4, publicar alterações, fazer upload de
firmware ou acionar motores automaticamente. Falta de hardware não impede
implementar lógica e simulador, mas impede afirmar validação física.

Resultado esperado: um único comando verifica a configuração, o ciclo e as
decisões por cenários reproduzíveis; a mesma lógica recebe UART real na Raspberry
e entradas JSONL no notebook. A etapa termina com pendências físicas explícitas.
