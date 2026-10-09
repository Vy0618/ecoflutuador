# Operação, contratos e validação V4 consolidada

## Estrutura escolhida

O entrypoint continua **poc_raspberry/main.py**. `servidor.py` na raiz continua legado, sem uso operacional V4. Não houve arquivo movido, renomeado ou excluído. A árvore integral antes/depois e o inventário de alterações estão em `docs/audit/`. Preferimos ampliar a separação já existente sem quebrar os caminhos do Raspberry/testes/header C++.

```
V4/
├── ControleESP32.ino          firmware V4, motores desabilitados por padrão
├── sensors_v4.h              filtro de sensores + lease + framing testáveis
├── poc_raspberry/
│   ├── main.py               composição, ciclo e CLI V4
│   ├── config.yaml           configuração central, USB padrão
│   ├── core/
│   │   ├── camera.py         aquisição exclusiva, buffer e idade
│   │   ├── contracts.py      Detection/DetectorBackend sem OpenCV
│   │   ├── detector.py       adapter SSD legado, falha explícita
│   │   ├── decision.py       política de classes e três zonas
│   │   ├── state.py          janela e estados operacionais
│   │   ├── serial_link.py    framing, reconexão, heartbeat
│   │   ├── config.py         validação e variáveis de ambiente
│   │   ├── telemetry.py      schema, histórico limitado, métricas
│   │   ├── logging_config.py JSON escapado, rotação opcional
│   │   └── diagnostics.py    bancada sem comandos de movimento
│   ├── api/status_server.py  observabilidade local Flask
│   ├── api/templates/       apresentação de dados, sem vídeo
│   ├── mock/                câmera, detector, serial e runner
│   ├── tests/               testes Python e C++ nativo
│   └── models/              arquivos originais preservados
├── configs/                  serviço V4 de referência, não instalado
├── tools/                    compilação, benchmark e validação HTTP
├── docs/                     auditoria, operação, pendências e evidências
└── arquivos legados          preservados nos caminhos originais
```

## Fluxos e máquina de estados

HC-SR04 → ESP32 filtro → EVENT:START → UART → fila do Pipeline → RecognitionController → captura local → detector → Detection → DecisionEngine → a/w/d/s → UART → ESP32 → PWM, somente em produção explicitamente habilitada.

Sensores/GPS → ESP32 TEL → UART → Pipeline → snapshot local → API/dashboard. A API não tem rotas de movimento, potência ou shutdown. Não há dependência de Wi-Fi/servidor remoto para decidir. Só existe uma API no processo V4; os legados não devem ser iniciados.

| Estado/evento | Transição/comportamento |
|---|---|
| Inicial | WAITING, s, sem inferência |
| Borda START:1 | CONFIRMING, acomodação 0,1 s |
| Acomodação terminou | RECOGNIZING, consome somente novos frames |
| Resultado presente | TRACKING; política pode ignorar classe ou parar por fauna |
| START:0 | WAITING/s, inclusive quando recebido durante inferência |
| Sem detecção por 2 s | WAITING/s; START alto não rearma |
| Janela completa de 15 s | WAITING/s mesmo com detecção contínua |
| Falha crítica | FAULT/s |
| TEL válida depois de falha/reconexão | WAITING, nível START atual consumido; exige liberação e nova borda |

Janela/acomodação/perda/FPS/resolução são configuráveis. CSI continua opcional; USB V4L2 índice0 é padrão. Buffer consumido uma vez, ID monotônico da captura, descarte por idade >0,5 s; ausência de captura por 1 s encerra com FAULT. Um intervalo sem novo frame não vale como nova confirmação nem ausência de objeto. A câmera continua capturando em baixa resolução durante WAITING, mas não há inferência. Lock cooperativo por câmera em XDG_RUNTIME_DIR evita dois processos V4; programas legados não respeitam esse lock, portanto precisam permanecer desligados. No Windows o lock POSIX não está disponível e há aviso explícito.

## Interface de visão e decisão

`core.contracts.DetectorBackend.detect(frame) -> list[Detection]`. O frame é imagem BGR local. `Detection(bbox, class_name, confidence, frame_id=None)` preserva bbox interna **xywh** para compatibilidade; `to_result()` converte para o contrato público **xyxy**:

```json
{"class":"plastic_bottle","confidence":0.89,"bbox":[10,20,40,60],"center":[25,40],"frame_id":123}
```

O Pipeline atribui o ID do frame que realmente foi capturado. A decisão rejeita IDs repetidos/fora de ordem quando informados. Não há regra dentro do detector que converta objetos em comandos. Adapter SSD agora devolve todas as classes reconhecidas. `target_classes` antigo de ModelConfig permanece apenas por compatibilidade de construção; **a seleção é decision.target_classes**.

Política padrão: targets bottle/plastic_bottle/plastic_bag; fauna fish/turtle/bird; confidence >=0,45; fauna retorna STOP imediatamente, independentemente do tamanho da bbox de lixo. `fauna_priority=false` permite priorizar lixo em conflito; a alteração deve ser deliberada na calibração da política. Classes desconhecidas são ignoradas. Entre alvos aceitos, maior área vence. Área é uma heurística, não medida física de distância. Esquerda a, centro w, direita d, ausência s; 3 confirmações, histerese4%, tolerância à perda0,5 s. Resultado inválido para.

Backends: `legacy_ssd` é o adapter existente e continua falhando com os pesos incompatíveis. `mock` precisa ser solicitado explicitamente em dry-run; production rejeita esse backend. Modo mock sempre usa detector sintético. Um backend futuro pode usar `model.backend: pacote.adapter:criar_detector`; factory recebe a seção model e retorna objeto com detect(frame). O pacote é código local confiável instalado pelo operador. ONNX/YOLO/OpenVINO/modelo parceiro ainda **não estão implementados**: devem apenas adaptar suas saídas ao contrato e não alterar DecisionEngine. Input size, thresholds, paths e versão ficam em config; nenhuma troca automática de pesos foi feita.

## UART vigente

115200 baud, 8N1; ESP32 UART2 RX16/TX17, Raspberry /dev/serial0; newline LF, CR aceito. ESP32 recebe até32 caracteres por linha e descarta **toda** a linha longa até LF. Pi remonta bytes fragmentados, limita linha a16KiB e fila a256 mensagens; overflow gera parada. Framing não garante integridade elétrica: validar GND/níveis e fiação.

| Sentido | Mensagem | Uso |
|---|---|---|
| ESP→Pi | BOOT:READY | Boot; invalida estado anterior |
| ESP→Pi | EVENT:START:0/1 | HC-SR04 filtrado; nível também vem em TEL |
| ESP→Pi | TEL:{json} | schema1, uptime_ms, start, ultrasonic, net, gps, water, motors; 1 Hz |
| ESP→Pi | EVENT:NET:BLOCKED/PASS/FULL_SUSPECTED/CLEAR | Rede, contador autoritativo na TEL |
| ESP→Pi | CMD_OK:a/w/d/s/q/e, PWR_OK:1:45 | ACK textual existente |
| ESP→Pi | ERR:... | Falha, invalida comando local e para |
| Pi→ESP | a/w/d/s + LF | Navegação V4; envio somente quando muda |
| Pi→ESP | q/e, P1xxx/P2xxx | Compatibilidade/controle histórico; não usados pela decisão V4 |
| Pi→ESP | PING, STATUS? | Diagnóstico; não prolongam movimento |
| Pi→ESP | HB:a/w/d/... | Novo heartbeat, apenas renova comando já aceito |
| ESP→Pi | HB_OK | Renovação aceita |

Extensão aditiva `protocol_version:"1.1"`, `firmware_version:"4.1.0"`, `control_timeout_ms:1500` na TEL, mantendo schema1. A configuração oficial exige esses campos para permitir controle real, evitando usar firmware antigo sem failsafe. HB enviado a cada0,5 s pelo **loop principal**, jamais por thread independente: inferência travada deixa de renovar. Não há sequência nem retransmissão de movimento automática. ACKs são parseados, mas não têm timeout individual supervisionado; perda de direção em uma UART ainda ativa pode ser observada por divergência de HB e levar à parada. ACK não é prova de movimento físico.

Lease: comando recebido estabelece validade de1,5 s; HB só renova o **mesmo** comando ainda válido. HB atrasado/diferente não rearma. Expiração zera alvos e PWM para1000 µs imediatamente, sem rampa, emite ERR:CONTROL_TIMEOUT. O mesmo helper C++ é testado com wrap de millis. O limite depende do loop firmware continuar executando e inclui sua latência (pulseIn limitado25 ms); watchdog de tarefa/hardware ainda é pendência.

Reconexão: contador de sessão SerialLink invalida supressão anterior, força s, espera nova TEL válida e nova borda START. Redução do uptime é tratada como reinício (inclui wrap, de forma conservadora). Comando idempotente de movimento seta alvo; potência não implica movimento. START repetido alto não abre novas janelas.

## Failsafe e limites

| Falha | Resposta consolidada |
|---|---|
| Pi desligado/UART perdida/processo travado | ESP expira lease e para; Pi FAULT se ainda vivo |
| Comandos ausentes por >1,5 s | STOP local ESP, sem precisar receber s |
| Câmera ausente no setup | Falha explícita, não abre UART |
| Câmera sem novos frames >1 s | FAULT/s, cleanup e saída não zero |
| Detector lança erro | FAULT/s e cleanup; não substitui modelo |
| Inferência ultrapassa budget | Resultado descartado, FAULT/s; default YAML300 ms; lease protege travamento |
| HC-SR04 inválido | ESP para se estava movendo e recusa movimento; Pi FAULT pela TEL |
| pH/ST100/GPS ausentes | Dados null/sem fix; não são sensores de controle crítico |
| DS18B20 ausente | temperature_c=null; implementação pendente |
| API falha ao abrir porta | Log ERROR, controle continua sem API |
| Wi-Fi/servidor remoto cai | Controle local independente; exporter remoto ainda não existe |
| Erro inesperado no ciclo | FAULT/s, fecha câmera/UART/API |

ECO_ENABLE_MOTORS=0 permanece padrão. Nenhum upload ou acionamento foi feito. Não confundir teste C++ do algoritmo com validação elétrica ou compilação ESP32. Pinos12/14 e mapeamento de motores foram preservados. Nível de parada1000 µs é o mapeamento já existente: deve ser validado para os ESCs reais antes de operar. Serviços/watchdogs não substituem esse ensaio.

## Telemetria e servidor

GET `/telemetry` fornece [schema exemplificado em JSON](audit/telemetry-example.json), gerado pela implementação testada; timestamp ISO UTC, system/state/uptime/mode/error, navigation.command, vision/detected/class/confidence/zone/model_version/backend, sensors, gps e communication. Campos indisponíveis usam null; fix falso quando TEL não está conectada/recente. Nome turbidity_ntu evita unidade ambígua. Valores antigos de sensores podem permanecer no último snapshot: sempre interpretar junto de communication.telemetry_age_ms. `/status` preserva o contrato anterior, mais detalhado; `/telemetry` deve ser preferido para consumidores novos.

Endpoints: `/` dashboard HTML leve, `/health` liveness HTTP, `/status`, `/detections`, `/decision`, `/telemetry`, `/history`, `/diagnostics`. Todos só leitura. Health não afirma que motores/sensores estejam prontos. `/diagnostics` mede CPU do processo por intervalo, RSS atual Linux e temperatura apenas se host identificado como Raspberry. Histórico deque de100 snapshots: por mudança de estado/comando/classe/zona/conectividade/erro ou a cada5 s. Dashboard mostra últimos20 e consulta a cada5 s, sem polling sobreposto. Não há JPEG, vídeo, base64, WebRTC, controle remoto ou geocodificação externa.

**Servidor/dashboard local funcional**, testado com Flask test_client e sockets HTTP reais em127.0.0.1. Interface visual não foi inspecionada em navegador: nenhum browser conectado estava disponível. O servidor Werkzeug atual serve bancada/rede local confiável; não é configuração de exposição pública. API não exige autenticação, portanto não publicar GPS/telemetria na internet diretamente.

Plano objetivo para servidor remoto: processo Flask independente de câmera/serial, `POST /v1/telemetry` validado e `GET /devices/<id>/latest`, `/events`, `/health`; exporter em thread sem bloquear controle, timeoutHTTP1 s, fila limitada, envio por mudança com coalescência mínima1 s e heartbeat5–30 s; eventos identificados por device_id+boot_id+sequence para deduplicação. Persistência inicial SQLite com retenção por dias/quantidade, limite de disco e batch até20 registros. Cache offline prioriza eventos, descarta snapshots periódicos antigos antes de eventos, backoff1–60 s. Testar servidor indisponível, fila cheia, ordem e replay antes de habilitar. `telemetry.server_url`/ECO_SERVER_URL estão **reservados**, não enviam dados hoje. Não instalar servidor duplicado no Pi para esse fim.

## Configuração, logs e execução

Paths de modelo resolvidos relativos ao YAML, independentemente do cwd. YAML valida números/intervalos, três zonas, classes, backend de câmera, dimensões, flags e frequência de heartbeat. Overrides: ECO_SERIAL_PORT, ECO_CAMERA_BACKEND, ECO_DETECTOR_BACKEND, ECO_SERVER_URL (reservado), ECO_LOG_LEVEL. Arquivo local é opt-in via `-c`; não há merge automático. Configuração dos sensores continua nas constantes firmware: calibração real não pode ser inventada em YAML do Pi.

Logs usam json.dumps (incluindo aspas, newlines e traceback), timestamp UTC, níveis DEBUG/INFO/WARNING/ERROR. INFO registra START, transições, comandos e snapshot por mudança/5 s; DEBUG registra frame_id, resultados, confiança, bbox/centro, decisão e latência e tráfego UART. Nunca pixels. `logging.file` opcional ativa2MB×4 arquivos (~8MB incluindo atual). Sem arquivo usa stderr/journal. systemd limita taxa de log. Histórico de eventos é volátil; rotação de logs não equivale a cache remoto.

Da raiz do projeto, com Python contendo as dependências:

```bash
python3 -m unittest discover -s poc_raspberry/tests -v
python3 poc_raspberry/mock/run_mock.py --frames 100 --fps 10 --quiet
python3 poc_raspberry/main.py mock --simulate-start-after 2 --simulate-clear-after 10 --duration 12
python3 tools/verify_api.py
python3 tools/benchmark_mock.py --duration 30 --waiting
python3 tools/benchmark_mock.py --duration 30
python3 tools/compile_firmware.py
```

Bancada USB, sem abrir serial:

```bash
python3 poc_raspberry/main.py camera-test --duration 5
python3 poc_raspberry/main.py dry-run --detector-backend mock --simulate-start-after 2 --simulate-clear-after 8 --duration 10
python3 poc_raspberry/main.py dry-run --duration 10
```

O segundo comando testa webcam com detector de cor **explicitamente sintético**. O terceiro mantém o modelo legado e falha com o par incompatível. Nenhum deles envia UART. CSI só por configuração explícita PICAMERA2.

Diagnóstico físico, somente quando solicitado em bancada, motores desconectados: `python3 poc_raspberry/main.py uart-test --duration 5` ou `sensor-test`; ambos só enviam s/PING/STATUS? e leem dados. Sem teste físico executado aqui. Modo mock não abre serial real. Modo real é alias de production; só abre após habilitação explícita:

```bash
python3 poc_raspberry/main.py production -c poc_raspberry/config.local.yaml --allow-control
```

**Comando documentado, não executado**. Requer adapter/modelo compatível, firmware1.1 validado e habilitação de PWM deliberada para operação; não usar como teste automático. START por hardware, sem simulação permitida em produção.

## Serviços/processos

`configs/ecoflutuador-v4.service`: exemplo para /home/eco/EcoFlutuador, User=eco, produção, Restart=on-failure/10 s, máximo3 tentativas em120 s, SIGTERM/5 s, Conflicts=ecoflutuador.service, sem espera por rede. Não foi instalado, habilitado ou iniciado. `systemd-analyze verify` passou no host. Antes de instalar ajustar caminho/usuário/permissão UART/câmera e config.local. O serviço legado existente foi preservado.

No Raspberry real, inventariar com `systemctl list-unit-files`, `systemctl status ecoflutuador.service`, `ps -eo pid,comm,pcpu,pmem,rss`, `ss -ltnp` e `fuser /dev/video0 /dev/serial0`; confirmar cada PID/unidade antes de desativar. Nenhum processo/serviço do Raspberry foi acessado ou removido nesta tarefa. O mock de45 s foi encerrado e liberou API/câmera/serial simuladas.

## Dependências reproduzíveis de desenvolvimento

```bash
python3 -m venv .venv
.venv/bin/pip install -r poc_raspberry/requirements-dev.txt
.venv/bin/python -m unittest discover -s poc_raspberry/tests -v
```

No Raspberry, as bibliotecas do sistema podem ser usadas (python3-opencv, python3-numpy,
python3-serial, python3-yaml, python3-flask). Não instalar Picamera2 para testar USB.
OpenCV/NumPy já eram dependências de execução; requirements-dev só explicita o necessário
para o host. Versões efetivamente usadas nesta auditoria estão em audit/environment.txt.
C++ requer g++/clang++/Zig; toolchain ESP32 é separado e não foi instalado nesta tarefa.

A zona geométrica de telemetria usa as mesmas fronteiras em pixels da decisão; o comando pode diferir temporariamente por histerese, confirmação ou STOP por fauna. Mensagens UART mantêm timestamp de recebimento e registros expirados na fila não renovam a conexão.
