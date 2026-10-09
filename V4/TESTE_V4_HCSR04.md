> Documento histórico anterior à consolidação. Para comportamento vigente, consulte [Operação V4](docs/OPERACAO_V4.md) e [resultado da auditoria](docs/RESULTADO_V4.md).

# Teste V4 — HC-SR04 e sensor da rede

## Segurança e preparação

Não executar motores durante estes testes. `ECO_ENABLE_MOTORS=0` é o padrão do
firmware: não conecta PWM aos ESCs. Não foi feito upload nesta implementação.
Manter motores desconectados também nos testes de bancada. O ECHO utiliza o
divisor resistivo externo para 3,3 V previsto pelo projeto; nenhuma compensação
por software é aplicada. Ver [PINAGEM_V4.md](PINAGEM_V4.md).

## Algoritmo e parâmetros

Todas as configurações de sensores ficam no início de `ControleESP32.ino`.

| Parâmetro | Inicial |
|---|---:|
| Período HC-SR04 | 100 ms (~10 Hz) |
| Timeout de pulseIn | 25.000 µs |
| Pulso TRIG / estabilização LOW | 10 µs / 2 µs |
| Faixa válida | 2–400 cm |
| Mediana | últimas 5 leituras válidas |
| Calibração | 30 medianas após encher janela (34 leituras, ~3,4 s) |
| Queda para ativar START | ≥15 cm |
| Queda para liberar START | ≤10 cm |
| Confirmações START / livre | 3 / 5 leituras filtradas consecutivas |
| Adaptação do baseline | alpha 0,005 por leitura livre |
| HW-870 ativo | LOW, configurável |
| Debounce da rede | 50 ms |
| Suspeita de rede cheia | 8.000 ms bloqueada |
| Limpar suspeita | 5.000 ms continuamente livre |

A mediana pode exigir duas leituras adicionais para mudar de patamar. Por exemplo,
com janela cheia em 60 cm, cinco amostras brutas de 40 cm dão três confirmações
filtradas e ativam START. Para retornar a 60 cm são sete brutas: duas de troca da
mediana e cinco livres. Uma leitura baixa isolada não ativa. Leituras zero, timeout,
NaN, infinito e fora da faixa são rejeitadas; quebram sequências de confirmação e
não entram na janela. Não limpam START por si sós.

Durante CALIBRATING, manter somente água no campo do sensor. O baseline é a média
das medianas de calibração. Depois só se adapta lentamente em região livre, sem
objeto bruto nem filtrado. Congela durante START, confirmação e faixa de histerese.
`valid=false` identifica a última leitura inválida; a distância e delta publicados
nessa situação são `null`. CALIBRATING termina apenas com amostras válidas suficientes.

O bloqueio da rede começa após debounce. Uma ativação estável menor que 8 s seguida
de liberação conta uma passagem; uma ativação longa não conta passagem. `PASS` e
`CLEAR` podem aparecer juntos na liberação curta. Na longa, `FULL_SUSPECTED` aparece
uma vez; `CLEAR` só aparece após os 5 s livres. `passage_count` é volátil e zera no
reboot, que pode ser identificado por `BOOT:READY`/`uptime_ms`.

## Protocolo compatível

`TEL:{json}` permanece com `schema:1`: evolução aditiva. Permanecem `uptime_ms`,
`start`, `gps`, `water` e `motors`, com os campos anteriores. `start.detected` espelha
`ultrasonic.start_detected`. `water.turbidity_digital` permanece `null` porque GPIO 32
é agora ECHO. Novos consumidores aceitam TEL antigo sem os novos objetos.

```json
{
  "ultrasonic": {
    "enabled": true, "valid": true, "distance_cm": 41.5,
    "baseline_cm": 60.2, "delta_cm": 18.7, "calibrated": true,
    "start_detected": true, "state": "READY"
  },
  "net": {
    "enabled": true, "blocked": false, "blocked_ms": 0,
    "passage_count": 4, "full_suspected": false
  }
}
```

Eventos são linhas UART, preservando o protocolo textual de controle:
`EVENT:START:1`, `EVENT:START:0`, `EVENT:NET:BLOCKED`, `EVENT:NET:PASS`,
`EVENT:NET:FULL_SUSPECTED`, `EVENT:NET:CLEAR`. HTTP transmite somente JSON; UART
continua com comandos/ACK/eventos textuais e TEL JSON. Nunca há imagem ou vídeo.
Um evento PASS não incrementa o contador local, evitando duplicar a contagem de
TEL; a contagem autoritativa sempre é a da ESP32. Eventos atualizam o estado da rede.

## Raspberry e decisão

WAITING → START confirmado pela ESP32 → CONFIRMING (0,1 s de acomodação) →
RECOGNIZING → detecção válida → TRACKING. START:0 interrompe imediatamente a decisão
e retorna a WAITING/s, inclusive se recebido durante a inferência. Dois segundos
sem detecção retornam a WAITING; requer liberação e novo START para rearmar, evitando
reconhecimento infinito com START preso em 1. Telemetria também reconcilia o nível
START caso um evento seja perdido.

Direções precisam de 3 detecções consecutivas; histerese é 4% da largura; ausência
breve é tolerada por 0,5 s antes de comandar s. As zonas continuam proporcionais,
com maior bbox como alvo: esquerda a, centro w, direita d, sem alvo s. O motor de
decisão mantém defaults legados para chamadas antigas; o Pipeline aplica defaults V4
mesmo quando o YAML antigo não contém os parâmetros novos.

Serial ausente, telemetria expirada (>3 s), reboot, erro ESP32 ou falha de envio
levam a FAULT/s. Uma nova TEL válida permite recuperação. A última TEL válida não
é apagada por JSON inválido; sua idade continua aumentando. O estado `serial_connected`
exige porta aberta e TEL recente. No dry-run/mock é false, pois não há UART física.
`last_error` retém o diagnóstico mais recente, inclusive após recuperação.

A API atende `/health`, `/status`, `/detections`, `/decision`; `/status` inclui
`operational_state`, `ultrasonic`, `net`, `environmental` (espelho de `water`),
`serial_connected`, `telemetry_age_ms`, `camera_backend`, `recognition_active` e
`last_error`. `/decision` inclui comando anterior/atual, motivo e timestamp Unix da
última mudança. `/health` indica processo HTTP vivo, não prontidão dos sensores.

## Comandos de teste

Da raiz, sem hardware:

```bash
python -m unittest discover -s poc_raspberry/tests -v
python poc_raspberry/mock/run_mock.py --frames 100 --fps 10 --quiet
```

O teste C++ usa `g++`/`clang++` no PATH, `CXX` apontando para um compilador, ou `ZIG`
apontando para `zig`/`zig.exe`. Sem compilador, registra um teste pulado explicitamente.
Ele compila e executa `sensors_v4.h`, sem GPIOs ou simulação duplicada em Python.

```bash
cd poc_raspberry
python main.py mock --simulate-start-after 2 --simulate-clear-after 10 --duration 12
python main.py dry-run --simulate-start-after 2 --simulate-clear-after 10 --duration 12
```

Dry-run usa câmera e modelo reais, mas nunca instancia a serial. É necessário o
backend de câmera já configurado e os arquivos do modelo existentes. Sem os flags
de simulação começa e permanece em WAITING. Simulação é rejeitada no modo real.
Para consultar a API: `curl http://localhost:8080/status`. Não executar os servidores
legados nem o serviço antigo: eles ainda fornecem streaming. O processo V4 nunca
abre janela de vídeo, rota MJPEG ou desliga a Raspberry.

## Compilação ESP32 (sem upload)

Dependências existentes: core Arduino ESP32, ESP32Servo e TinyGPSPlus. Não há nova
biblioteca de sensor nem dependência Python de execução. Werkzeug já é dependência
do Flask. Um compilador C++ nativo é necessário apenas para o teste de sensores.

```bash
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install ESP32Servo TinyGPSPlus
python tools/compile_firmware.py
```

O helper copia somente `.ino` e header para um sketch temporário `ControleESP32/`
e executa `arduino-cli compile --fqbn esp32:esp32:esp32`; salva em `build/firmware/`.
O caminho pode ser passado com `--cli`. **Não faz upload nem abre portas.** A opção
`--enable-motors` existe somente para futura compilação operacional, fora destes testes.
O arming operacional passa a ser temporizado sem `delay()`.

Referência de compilação: [Arduino CLI oficial](https://docs.arduino.cc/arduino-cli/getting-started).

## Roteiro de bancada, motores desconectados

1. Conferir a pinagem e o divisor do ECHO. Usar o firmware padrão sem PWM.
2. Posicionar sobre água livre e observar CALIBRATING → READY e baseline próximo
   da distância medida; ruído próximo de 60 cm não deve gerar START.
3. Aproximar objeto para uma redução ≥15 cm; confirmar somente um START:1.
4. Manter objeto; baseline não deve acompanhá-lo. Retirar e aguardar as cinco
   leituras filtradas livres; confirmar somente um START:0.
5. Interromper ECHO e conferir valid=false, sem atualização de baseline.
6. Bloquear HW-870 brevemente e liberar; contador aumenta exatamente uma vez.
7. Bloquear por ≥8 s; full_suspected fica true sem passagens repetidas. Liberar por
   5 s e conferir CLEAR. Ajustar nível ativo caso o módulo opere invertido.
8. Confirmar estados e decisões na API, sem janela ou streaming. Bancada física,
   aquisição acústica real e desempenho no Raspberry exigem validação no equipamento.

## Resultados da execução no workspace

- Antes das alterações: 43 testes existentes passaram.
- Runner mock V4: passou, observando a/w/d/s, TRACKING e WAITING.
- Pipeline mock com START/liberação temporizados: passou e encerrou câmera/API.
- `compileall` da POC e do helper: passou.
- **Teste adicional com DNN real falhou**, mesmo com câmera sintética e serial
  bloqueada por mock: OpenCV 4.13.0 informou `Const input blob for weights not found`
  ao carregar `FeatureExtractor/MobilenetV3/Conv/Conv2D`. O `.pb` existente contém
  nomes `MobilenetV1` e não contém `MobilenetV3`; o `.pbtxt` selecionado é V3 Large.
  Portanto o par de modelo já existente é incompatível. Modelos e caminhos de
  configuração foram preservados. Para executar dry-run/real com inferência, fornecer
  um par de pesos/configuração correspondente em `config.local.yaml`; não basta
  renomear o arquivo. A lógica V4 com detector mock foi testada separadamente.
- Testes físicos de acústica, GPIO/UART, câmera Raspberry e motores não executados.

- **Suíte final: 58 testes passaram, sem testes pulados**, usando Zig 0.16.0 para
  executar o C++ dos sensores e Python 3.14.7 para a POC. Foram preservados os 43
  testes antigos. As asserções nativas cobrem calibração, ruído, leitura isolada,
  3 confirmações, 5 livres, baseline congelado, rejeição de inválidos, histerese,
  passagem única, debounce, bloqueio de 8 s e liberação de 5 s.
- As primeiras tentativas do compilador nativo foram interrompidas durante a
  construção desnecessária do runtime; o executor mínimo inicialmente apresentou
  erros de headers/símbolos de runtime. A configuração de teste Windows foi corrigida
  e a suíte completa foi executada novamente com sucesso. Zig ainda emite um aviso
  de argumento interno não utilizado (`-fno-rtlib-defaultlib`), sem falha no teste.
- Zig e Arduino CLI foram obtidos somente em diretórios temporários; nenhuma nova
  dependência de execução foi adicionada ao projeto. ESP32Servo 3.2.1 e TinyGPSPlus
  1.0.3 foram instalados no diretório temporário de compilação.

Compilação ESP32: em verificação.
