# Auditoria EcoFlutuador V4 — 16/09/2026

Este documento registra o estado encontrado **antes das mudanças de código**.
Inventário integral: [árvore](audit/tree-before.txt), [hashes SHA256 e tamanhos de todos os 67 arquivos](audit/original-manifest.json).
Snapshot original preservado em `/tmp/eco-v4-original.tar.gz` (temporário; copiar para armazenamento durável antes de limpar /tmp).
Não há AGENTS.md. `.git`, `.agents` e `.codex` são diretórios vazios protegidos nesta cópia; `git status` falha. Não há histórico Git acessível para preservar via commit.

## Mapa completo

| Pasta/arquivo | Função, dependências, classificação |
|---|---|
| `ControleESP32.ino` | Firmware V4: UART2 controle, UART1 GPS, ADC, HC-SR04, HW-870, PWM opcional; Arduino + ESP32Servo + TinyGPSPlus + sensors_v4.h |
| `sensors_v4.h` | Filtro/mediana/calibração relativa HC-SR04 e debounce/contador da rede; C++ sem hardware |
| `ControleESP32V2` | Firmware legado sem extensão; motores habilitados, USB, sem sensores; não executar |
| `servidor.py` | Flask legado manual, MJPEG, serial e câmera abertos ao importar; envia movimento **sem newline**, incompatível com framing V4 |
| `servidorSliders.py` | Flask legado manual/potência; MJPEG, serial/câmera globais, reconexão |
| `servidorUnificado.py` | Flask legado com DNN compartilhada entre captura e navegação: duas inferências concorrentes, JPEG contínuo, controle remoto |
| `object-ident.py` | Experimento legado, preview cv2.imshow, caminhos /home/eco/Desktop; falta import cv2; não é detector V4 |
| `Servidor 1.0/servidor.py` | Variante monolítica anterior; auto/manual/stream, modelo absoluto; inferência na captura, decisão separada em thread |
| `Servidor 1.0/index.html` | Interface manual com imagem/controles; não adequada ao dashboard de dados |
| `Servidor 1.0/script.js` | fetch move/power/modo/log, polling 1 s; innerHTML de log e controle manual; não reutilizar no controle V4 |
| `Servidor 1.0/style.css` | Estilos do painel legado; reaproveitáveis visualmente, sem valor arquitetural |
| `Servidor 1.0/readme` | Nota histórica de modularização |
| `ecoflutuador.service` | Unidade **legada**, /home/eco/servidor.py, usuário eco, Restart=always, multi-user.target |
| `ESP32-EcoFlutuador.nmconnection` | Perfil NetworkManager privado com autoconnect; só inicia se instalado/ativado no host; não divulgar credenciais |
| `diario` | Histórico: confusão /dev/video0 com serial; proposta antiga de modularização |
| `readme` | Arquivo vazio, sem instruções |
| `ESTRUTURA_V4.md` | Relatório anterior, mistura inventário inicial e mudanças; Git descrito não corresponde a esta cópia |
| `TESTE_V4_HCSR04.md` | Protocolo/sensores/testes anteriores; compilação estava “em verificação” |
| `PINAGEM_V4.md` | Pinagem atual coerente com firmware |
| `SENSORES_V4.md` | Índice de sensores com caracteres corrompidos |
| `.gitignore` | Caches, config local, logs, build; não inclui perfil privado de rede |
| `poc_raspberry/main.py` | **Entrypoint V4 correto**, CLI mock/dry-run/real, composição/ciclo/START/API; importa core/api/mock |
| `poc_raspberry/core/camera.py` | Captura em thread, buffer único consumível, USB/CSI, cópias redundantes, sem lock entre processos |
| `poc_raspberry/core/detector.py` | Adapter concreto SSD TensorFlow OpenCV; Detection xywh; filtra bottle dentro do detector |
| `poc_raspberry/core/decision.py` | Zonas/maior bbox, confirmação/histerese/perda; importa Detection do módulo OpenCV |
| `poc_raspberry/core/state.py` | WAITING/CONFIRMING/RECOGNIZING/TRACKING/FAULT e estado JSON |
| `poc_raspberry/core/serial_link.py` | PySerial, fila/framing no leitor, reconnect, valida TEL/ACK/START; sem ACK supervisionado |
| `poc_raspberry/core/__init__.py` | Exportações eager; importar estado/decisão também exige OpenCV e PySerial |
| `poc_raspberry/api/status_server.py` | Flask/Werkzeug em thread: health/status/detections/decision; sem stream, dashboard, ingestão ou histórico |
| `poc_raspberry/mock/camera_mock.py` | Geração de imagem sintética; interpolação pode sair da tela, desenho de zonas corta objeto |
| `poc_raspberry/mock/serial_mock.py` | Fila ACK simulada; flags de erro sem implementação, polling 1 ms |
| `poc_raspberry/mock/run_mock.py` | Exercita decisão e START em frames sintéticos; **não transmite comandos para MockSerial** |
| `poc_raspberry/mock/__init__.py` | Exporta mocks |
| `poc_raspberry/tests/test_decision.py` | 43 testes: zonas/resoluções/serial/serialização |
| `poc_raspberry/tests/test_v4.py` | 15 testes: estados, Pipeline, câmera consumível, UART fragmentada/reconnect/API e executor C++ |
| `poc_raspberry/tests/sensors_v4_test.cpp` | Asserções do header real, sem GPIO/PWM; usado por um teste Python |
| `poc_raspberry/tests/__init__.py` | Marcador de pacote |
| `poc_raspberry/config.yaml` | CSI padrão, 640×480/10 FPS, detector legado, UART /dev/serial0, API 8080 |
| `poc_raspberry/requirements.txt` | PySerial/PyYAML/Flask; OpenCV/NumPy apenas em comentários; sem lock de versões |
| `poc_raspberry/README.md` | Guia misturado com legado; pinos ESC 18/19 errados (reais 12/14), alegação falsa de timeout firmware, comandos CLI incompletos, exemplos de modelo não confiáveis |
| `poc_raspberry/models/frozen_inference_graph.pb` | 29.185.289 bytes, nomes MobilenetV1; incompatível com pbtxt V3 |
| `poc_raspberry/models/ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt` | Grafo textual V3, 182.178 bytes; não trocar/renomear para esconder erro |
| `poc_raspberry/models/coco.names` | Labels COCO, não dataset de classes Eco |
| `poc_raspberry/models/.gitkeep` | Instrução histórica de modelo (não vazio) |
| `tools/compile_firmware.py` | Staging temporário Arduino, compila sem upload; opção motores exige ação explícita |
| `build/firmware/` | 6 artefatos anteriores bin/bootloader/partitions/merged/elf/map; não comprovam compilação desta cópia |
| `**/__pycache__/` | 16 caches Python 3.14 de ambiente anterior; não são fonte, não removidos |

Nenhum par de arquivos é idêntico por SHA256. Existem **duplicações funcionais** entre os quatro servidores, detectores/zonas legados e POC, HTML/CSS/JS inline e separados, logging no runner e main. Não há JSON fonte, shell scripts, Docker, CI ou outro requirements oculto no inventário inicial. O trecho `/shutdown` recebido na solicitação não existe nos arquivos e não integra a arquitetura desejada.

## Arquitetura e entrypoints

V4: HC-SR04 → header de filtro → EVENT/TEL → SerialLink → fila Pipeline → RecognitionController → câmera consumível → Detector → DecisionEngine → a/w/d/s → UART → firmware. Sensores → TEL → Pipeline → API local JSON. Tudo de controle local; nenhuma dependência de servidor remoto.

Entrypoints executáveis: main.py (V4); mock/run_mock.py (bancada V4); ControleESP32.ino setup/loop (V4); tools/compile_firmware.py (build); unittest (testes); quatro servidores Flask, object-ident.py e ControleESP32V2 (legado). Não há servidor remoto V4 existente.

## Problemas prioritários

P0: ausência de lease/timeout no ESP32; PWM pode manter último comando indefinidamente. STOP usa rampa, não parada imediata. Overflow do framing firmware aceita sufixo após limpar buffer. Reconexão conserva supressão do último comando no Pi. HC inválido mantém START alto; Pi ignora valid=false. Recuperação automática de FAULT por qualquer TEL pode rearmar com START alto. Inferência travada bloqueia controle Pi.

P1: janela só limita ausência de detecção (TRACKING ilimitado); não há identidade/timestamp de captura; consumo único não mede idade. Mock não testa transmissão. Detector é concreto e filtra fauna. API indisponível aborta setup sem cleanup. Camera falha gera até 100 warnings/s. Logs “JSON” por interpolação quebram com aspas/tracebacks; stdout a cada frame mesmo WAITING. FPS médio inclui espera. Caminhos dependem do cwd; camera index ausente. Config sem validação/env, campos min_fps/max_inference_ms/print_fps_interval ignorados. Sem envio/cache/histórico/dashboard. DS18B20 ausente.

P2: validação TEL aceita schema-only e tipos ambientais incompletos; GPS altitude/velocidade têm freshness parcial; sensor analógico sem diagnóstico elétrico; rede tem perfil aparentemente malformado (não alterado); documentação contraditória.

## Sensores encontrados

| Sensor | Implementação/pinos/dependências | Teste/calibração |
|---|---|---|
| HC-SR04 | Implementado TRIG33/ECHO32; pulseIn 25 ms, período 100 ms, mediana5, baseline30, histerese15/10 cm | C++ passa; sem teste acústico; thresholds provisórios exigem experimento; divisor ECHO externo |
| ST100 | Parcial ADC35, média8, raw/volts, desabilitado; conversão NTU desabilitada | Sem teste/calibração real; coeficientes existentes não são calibração válida |
| pH4502C | Parcial ADC34, média8, raw/volts, desabilitado | Sem teste/calibração real; PH_CALIBRATED=false |
| DS18B20 | Ausente; nenhum pino definido, OneWire/DallasTemperature ausentes | Depende de montagem e pinagem aprovada; não inventar |
| GY-NEO6MV2 | Parcial UART1 RX27/TX26 9600, TinyGPSPlus, fix <5 s, desabilitado | Sem GPS real/testes NMEA |
| HW-870 extra | Implementado GPIO25 LOW, debounce50 ms, bloqueio8 s, liberação5 s | Header C++ testado, elétrica não |

## Baseline reproduzido

Host disponível: Ubuntu x86_64, Python 3.12.3, **não Raspberry**. Primeiro unittest: 2 erros de importação, 0 testes reais executados, cv2 ausente (dependência). Mock e dry-run bloqueados por mesma causa. Instalação isolada em /tmp, sem modificar fontes; versões em audit/environment.txt.

Com dependências: **58 passaram, 0 falhas, 0 erros, 0 skips**, sem warnings na suíte; C++ g++ -std=c++11 também passou com -Wall -Wextra -pedantic. Todos os 21 Python passaram AST/sintaxe. Nove módulos principais importados sem hardware. Legados não importados deliberadamente: efeitos colaterais de serial/câmera/threads; análise estática completa.

Runner 100 frames/10 FPS: a,d,s,w e WAITING/TRACKING, exit0. CLI mock 3 s com START/liberação: exit0 após permitir socket local; 29 frames, cleanup câmera/serial/API. Primeira tentativa socket bloqueada pelo sandbox (ambiente), expôs falta de cleanup de setup (código).

Dry-run original: exit1, Picamera2 ausente. Detector isolado: `Const input blob for weights not found`, OpenCV 5.0.0 também tenta engine antigo e falha; evidência binária V1 vs V3 confirma incompatibilidade existente. Sem substituir modelo. Arduino: tentativa helper falhou `FileNotFoundError: arduino-cli` (toolchain ausente). Artefatos antigos não contam como build validado.

Warnings de instalação: cache pip não gravável e DNS no sandbox; resolvidos com venv temporário/download autorizado. Não são warnings dos testes.

## Processos, autostart e recursos

Namespace de processos acessível mostrou apenas executor/ shell/ps, nenhum servidor Eco identificável. systemctl não conectou ao bus (sandbox); busca de referências Eco nas unidades/cron acessíveis não identificou instalação. **Não se conclui que serviços do Raspberry estejam desativados**, pois Raspberry não acessível. Nenhum processo removido/desativado nesta auditoria.

Serviço legado pode iniciar em multi-user.target **se instalado e habilitado**; perfil NetworkManager pode autoconectar **se instalado**. Os quatro servidores competem por câmera0, ttyUSB0 e porta8080. Unificado faz dupla inferência, todos codificam JPEG continuamente. Não executar. Medições deste notebook não são medidas de CPU/RAM do Pi.

## Proposta anterior à consolidação

Manter `poc_raspberry/` (nome histórico, código V4), firmware/header raiz e os testes nos caminhos atuais. Acrescentar contratos/adapter, config, logs/telemetria, dashboard de dados na API existente, docs e unidade systemd V4 não instalada. Identificar legado via README sem mover seus arquivos. **Nenhum movimento necessário**: imports atuais, referências do helper C++ e instalação permanecem estáveis. Não criar árvore de dez pacotes vazios.

Impactos controlados: Detection continua exportada pelo adapter antigo, bbox interna xywh preservada com conversão pública xyxy; testes antigos mantidos; entrypoint preservado com aliases/modos adicionais; unidade nova aponta explicitamente ao V4; modelo antigo só carrega quando backend solicitado. Flask já atende observabilidade: migrar FastAPI agora acrescentaria dependência e migração sem benefício medido. Servidor remoto/cache persistente pode ser etapa posterior com contrato objetivo; dashboard local atende bancada imediatamente.

Ordem: segurança firmware + core e regressões; contratos/decisão/config; API/schema/logs; performance/mock e relatório final. Sem motores, upload, streaming, exclusões ou instalação de serviços.
