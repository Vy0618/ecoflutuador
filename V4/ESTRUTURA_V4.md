> Documento histórico anterior à consolidação. Para comportamento vigente, consulte [Operação V4](docs/OPERACAO_V4.md) e [resultado da auditoria](docs/RESULTADO_V4.md).

# Análise do workspace e evolução V4

Análise realizada antes das alterações. O workspace contém duas gerações de
software Raspberry: servidores monolíticos antigos e uma POC modular mais recente.
Não foi encontrado `AGENTS.md` no projeto. O Git detectado pertence a um diretório
ancestral do workspace; nenhum commit, push ou operação de staging foi realizado.

## Inventário existente

| Caminho | Papel e comportamento encontrado |
|---|---|
| `ControleESP32.ino` | Firmware principal ESP32: ESP32Servo, TinyGPSPlus, UARTs independentes, rampa de motores, ADC, START digital, TEL schema 1 e comandos de diagnóstico |
| `ControleESP32V2` | Firmware histórico sem extensão `.ino`; controle de ESCs e protocolo de potência antigo |
| `servidor.py` | Servidor Flask legado; abre serial e câmera na importação, controle manual e streaming MJPEG |
| `servidorSliders.py` | Variante legada com sliders de potência e streaming |
| `servidorUnificado.py` | Variante legada com detector DNN, modo automático, controle manual e streaming |
| `Servidor 1.0/servidor.py` | Variante Flask legada com interface em arquivos separados e streaming |
| `Servidor 1.0/index.html`, `script.js`, `style.css`, `readme` | Interface e documentação da variante antiga |
| `object-ident.py` | Experimento independente de detecção com janela OpenCV e caminhos absolutos do modelo |
| `ecoﬂutuador.service` (`ecoflutuador.service` no disco) | Serviço existente aponta para `/home/eco/servidor.py`, portanto ainda é legado |
| `ESP32-EcoFlutuador.nmconnection` | Configuração particular de rede; preservada, sem reproduzir credenciais |
| `readme`, `diario` | Documentação/histórico; diário relata confusão anterior entre câmera e porta serial |
| `.gitignore` | Ignora dependências locais, caches Python, configuração local e logs |
| `SENSORES_V4.md` | Planejamento anterior: HW-870 em 33 e ST100 digital em 32; substituído pela pinagem desta etapa |
| `poc_raspberry/main.py` | Pipeline e CLI `mock`, `dry-run`, `real`; inicialmente fazia inferência a cada frame e apenas registrava START |
| `poc_raspberry/core/camera.py` | Captura assíncrona com buffer único; backends OpenCV e Picamera2, sem streaming |
| `poc_raspberry/core/detector.py` | SSD MobileNet v3 Large via OpenCV DNN; classes COCO, filtro de confiança e classe bottle |
| `poc_raspberry/core/decision.py` | Maior bounding box, zonas proporcionais e comandos a/w/d/s; inicialmente sem confirmação temporal |
| `poc_raspberry/core/serial_link.py` | PySerial, parser TEL/ACK/START, reconexão; havia tentativa de encerrar/join da própria thread na reconexão |
| `poc_raspberry/core/state.py` | DetectionState serializável, coordenadas normalizadas e bbox |
| `poc_raspberry/api/status_server.py` | Flask JSON: originalmente somente `/health` e `/status`; `/detections` e `/decision` foram adicionados nesta etapa |
| `poc_raspberry/mock/camera_mock.py` | Frames sintéticos em memória com garrafa verde, sem webcam |
| `poc_raspberry/mock/serial_mock.py` | Serial simulada com ACKs e fila em memória |
| `poc_raspberry/mock/run_mock.py` | Runner de bancada; recriava o motor de decisão a cada frame, impedindo estabilidade temporal |
| `poc_raspberry/config.yaml` | Câmera PICAMERA2 640×480/10 FPS, modelo, UART `/dev/serial0`, API e parâmetros de execução |
| `poc_raspberry/requirements.txt` | PySerial, PyYAML, Flask; OpenCV e NumPy fornecidos pelo sistema no Pi |
| `poc_raspberry/README.md` | Instalação e operação da POC |
| `poc_raspberry/models/` | `.gitkeep`, `frozen_inference_graph.pb`, `ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt`, `coco.names`; teste adicional detectou incompatibilidade V1/V3 no par existente |
| `poc_raspberry/tests/test_decision.py` | 43 testes existentes: decisões, resoluções, protocolo e serialização |
| `core/__init__.py`, `mock/__init__.py`, `tests/__init__.py` | Marcadores de pacotes dentro da POC |

## Fluxo V4 implementado

HC-SR04 → mediana/calibração/START na ESP32 → UART → fila e parser na Raspberry
→ WAITING/CONFIRMING/RECOGNIZING/TRACKING/FAULT → detector existente → decisão
estável → comando serial somente em real e quando mudar. HW-870 → eventos de rede
e telemetria. Flask publica dados JSON; nenhum frame é exportado.

A Raspberry permanece ligada. Encerrar o processo libera câmera, serial e HTTP;
não desliga o sistema operacional. Em WAITING a captura pode continuar, mas não
há inferência. Cada quadro capturado é consumido uma única vez, evitando que uma
câmera travada gere confirmações falsas a partir do mesmo buffer.

Os servidores legados, serviço systemd existente, Wi-Fi e credenciais não foram
alterados nem executados. Para V4, iniciar `poc_raspberry/main.py`; o serviço antigo
não migra automaticamente e continua incompatível com a exigência de não streaming.

## Arquivos novos e alterados

| Arquivo | Alteração |
|---|---|
| `ControleESP32.ino` | Pinagem nova, aquisição HC-SR04 limitada a 25 ms, sensores de START/rede, TEL aditivo e compilação de teste sem PWM; removido delay de arming |
| `sensors_v4.h` (novo) | Algoritmos C++ de mediana/baseline/histerese/confirmação e debounce/passagem/lotação, independentes do hardware |
| `core/state.py` | Máquina operacional, timeout e rearme após novo START |
| `core/decision.py` | Confirmação, tolerância a perda, histerese e metadados de decisão; compatibilidade dos consumidores antigos |
| `core/serial_link.py` | Eventos NET, JSON estrito e validação, leitura fragmentada, limites de buffer, conexão e reconexão corrigidas |
| `main.py` | START condiciona inferência, fila serial, retenção/idade TEL, parada segura, simulação explícita e execução com duração limitada |
| `core/camera.py`, `mock/camera_mock.py` | Consumo único do frame |
| `api/status_server.py` | Quatro endpoints JSON, estado completo e encerramento real do servidor HTTP |
| `mock/run_mock.py` | Exercita o Pipeline V4 com frames e START sintéticos e decisão persistente |
| `config.yaml` | Apenas novos parâmetros de decisão/reconhecimento; valores particulares anteriores preservados |
| `tests/test_v4.py`, `tests/sensors_v4_test.cpp` (novos) | Regressões Python e testes nativos do mesmo C++ do firmware |
| `tools/compile_firmware.py` (novo) | Compila o sketch existente em diretório temporário com nome exigido pelo Arduino; nunca faz upload |
| `.gitignore` | Acrescenta `build/` para artefatos de compilação |
| `PINAGEM_V4.md`, `TESTE_V4_HCSR04.md`, `ESTRUTURA_V4.md` (novos) | Pinagem vigente, protocolo, testes e análise do projeto |
| `SENSORES_V4.md`, `poc_raspberry/README.md` | Orientação atualizada para esta etapa; instrução de teste de movimento substituída por PING |

Os caminhos `core/`, `api/`, `mock/`, `tests/` e `config.yaml` da tabela acima são
relativos a `poc_raspberry/`. Detector, modelos, requirements e testes antigos
continuam sendo reaproveitados.
