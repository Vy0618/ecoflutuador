# Setup e testes — EcoFlutuador V4.1

Este guia reúne a instalação, a configuração e os testes do reconhecimento,
do OLED e dos motores, no computador e na Raspberry Pi 5 com ESP32-WROOM-32.
A apresentação, o funcionamento, o hardware e as fontes estão no
[README principal](../README.md).

**Execute todos os comandos na raiz do projeto**, mesmo que este documento
esteja dentro de `docs/`. A câmera é USB e o vídeo é exibido por padrão;
`--no-display` permite executar sem janela.

No padrão OLED, câmera e comandos funcionam continuamente com `--serial-port`,
sem HC-SR04. No modo de motores, o padrão exige a janela de 30 s do sensor.
Sem serial, a câmera e a detecção também funcionam continuamente.

## Conteúdo

- [Instalação](#instalação)
- [Seleção de OLED ou motores](#seleção-de-oled-ou-motores)
- [Teste apenas do reconhecimento](#teste-apenas-do-reconhecimento)
- [Teste no computador com ESP32](#teste-no-computador-com-esp32)
- [Setup na Raspberry Pi 5 com ESP32](#setup-na-raspberry-pi-5-com-esp32)
- [Configuração do reconhecimento](#configuração-do-reconhecimento)
- [Comandos úteis](#comandos-úteis)
- [Logs e acompanhamento](#logs-e-acompanhamento)
- [Validação e próximos passos](#validação-e-próximos-passos)

## Instalação

### Programa Python

No Linux, na raiz do projeto:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

No Windows, em PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe object-ident.py
```

Nos demais comandos deste guia, o Windows usa `.venv\Scripts\python.exe` no
lugar de `.venv/bin/python`, e uma porta como `COM3` no lugar de `/dev/ttyUSB0`.

A visualização precisa do OpenCV com suporte gráfico e de uma sessão gráfica
acessível. O mesmo `opencv-python` atende aos modos com vídeo e headless.

### Firmware e ferramentas

O PlatformIO instala as bibliotecas declaradas em `platformio.ini`. Instale o
[PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/index.html)
ou use o terminal do PlatformIO no VS Code para executar `pio`. Na Arduino IDE,
instale o core Arduino-ESP32, selecione **ESP32 Dev Module** e instale Adafruit
SSD1306 e Adafruit GFX Library com suas dependências. Essas bibliotecas são
necessárias para compilar o sketch também quando o modo de saída é motores.

Confira qual instalação do PlatformIO o terminal usa:

```bash
type -a pio
pio --version
```

Se `/usr/bin/pio` mostrar o erro `resultcallback`, o terminal está usando uma
instalação antiga incompatível com o Click do sistema. Neste computador existe
um PlatformIO 6.1.19 em `~/.platformio/penv/bin/pio`. Use-o diretamente:

```bash
~/.platformio/penv/bin/pio run --project-dir firmware/ControleESP32 --environment esp32-usb --target upload --upload-port /dev/ttyUSB0
```

Para que `pio` use essa instalação na sessão atual do Bash:

```bash
export PATH="$HOME/.platformio/penv/bin:$PATH"
hash -r
pio --version
```

O caminho depende da instalação de cada máquina. O
[guia do PlatformIO](https://docs.platformio.org/en/latest/core/installation/troubleshooting.html#multiple-platformio-cores-in-a-system)
descreve os conflitos entre versões instaladas.

Neste ambiente local, `.venv/bin/pio` também aponta para o PlatformIO 6.1.19.
Reative o venv e limpe o cache de comandos do Bash para usar esse caminho:

```bash
source .venv/bin/activate
hash -r
command -v pio
pio --version
```

O caminho esperado é o `pio` dentro de `.venv/bin/`. Esse vínculo pertence ao
ambiente local; ao criar um novo venv em outra máquina, prepare o PlatformIO nela.

## Seleção de OLED ou motores

A saída e o sensor são escolhidos ao iniciar o Python:

### OLED sem sensor — padrão

Executa o reconhecimento continuamente e mostra os comandos no OLED, sem
depender do HC-SR04 e sem acionar os motores.

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0 --output oled
```

### OLED com ultrassônico

Mantém o reconhecimento em espera até uma leitura válida abaixo de 15 cm.
Depois, exibe os comandos no OLED durante a janela de 30 segundos.

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0 --output oled --ultrasonic
```

### Motores com ultrassônico — padrão dos motores

Usa os motores para a navegação, com ativação pelo HC-SR04 e janela de
30 segundos. Esse é o padrão ao selecionar `--output motors`.

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0 --output motors
```

### Motores sem ultrassônico

Executa o reconhecimento e envia os comandos aos motores continuamente,
sem aguardar o sensor e sem o limite de 30 segundos.

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0 --output motors --no-ultrasonic
```

As portas são exemplos: use a porta correspondente à ligação e ao perfil
gravado na ESP32. As paradas por alvo ausente, região inferior e falha de
comunicação continuam funcionando em todos os modos.

| Argumento | Saída |
|---|---|
| `--output oled` | Exibe os comandos no OLED; nenhum PWM é gerado |
| `--output motors` | Controla os ESCs e motores |
| `--ultrasonic` | Exige o disparo do sensor e limita a janela a 30 s |
| `--no-ultrasonic` | Reconhecimento contínuo, sem sensor |

**Grave esta versão do firmware uma vez.** Depois, a mudança entre esses modos
é enviada pela UART, sem editar variáveis ou regravar a cada teste. O padrão
com serial é OLED sem sensor; os argumentos de modo exigem `--serial-port`.
`--no-display` controla apenas o vídeo no computador. O teste visual usa
OLED SSD1306 de endereço I²C `0x3C`.

### Ligações da saída

| Componente | ESP32-WROOM-32 |
|---|---|
| OLED SDA | GPIO 23 (`OLED_SDA`, valor atual do firmware) |
| OLED SCL | GPIO 22 |
| OLED GND | GND |
| OLED VCC | 3,3 V, com módulo compatível com essa alimentação |
| Sinal do ESC 1 / motor esquerdo | GPIO 12 |
| Sinal do ESC 2 / motor direito | GPIO 14 |
| Referência dos ESCs | GND comum com a ESP32 |
| HC-SR04 TRIG | GPIO18 |
| HC-SR04 ECHO | Adaptação de nível de 5 V para 3,3 V → GPIO19 |

Para o modo motores, os GPIOs fornecem sinais aos ESCs; os ESCs e motores usam
alimentação própria. Faça o primeiro teste de acionamento sem hélices. A parada
`s` aplica o pulso mínimo de 1000 µs aos ESCs; ela não corta a alimentação elétrica.

A tela usa I²C nos pinos SDA23/SCL22, conforme a
[API I²C do Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html).
Mais detalhes da tela estão no [guia OLED](TESTE_OLED.md).
O HC-SR04 não precisa estar conectado no teste OLED padrão. Quando habilitado,
o HC-SR04 clássico usa VCC de 5 V; a fonte real ainda precisa ser definida.
Não conecte ECHO diretamente ao GPIO19. Confira GND, alimentação e adaptação
nas [ligações previstas do sensor](HARDWARE.md#hc-sr04-ligações-previstas).

### Seleção do canal de comunicação

A saída OLED/motores e o canal de comunicação são escolhas independentes:

| Cenário | Perfil PlatformIO | Canal de comandos |
|---|---|---|
| Computador com cabo USB conectado à ESP32 | `esp32-usb` | UART0 pelo conversor USB da placa |
| Raspberry com fios nos GPIOs | `esp32` | UART2 da ESP32: RX2 (GPIO 16), TX2 (GPIO 17) |

Com PlatformIO, mantenha o valor padrão `ECO_SERIAL_USB=0` no sketch; o perfil
`esp32-usb` define `1` na compilação. Pela Arduino IDE, altere essa definição para
`1` no teste USB ou `0` na montagem com UART2. Grave novamente depois de mudar.

No perfil UART2, o cabo USB continua servindo para gravação. Os comandos e as
respostas do protocolo passam por RX2/TX2 (GPIOs 16/17).

## Teste apenas do reconhecimento

Conecte a câmera USB ao computador, instale as dependências e execute:

```bash
.venv/bin/python object-ident.py
```

A janela deve mostrar a câmera, as bounding boxes, as regiões, a garrafa
selecionada e o comando decidido. O terminal registra cada inferência.
Sem `--serial-port`, as decisões ficam no terminal e no arquivo de log, sem
depender do HC-SR04.

Para outra câmera ou uma execução limitada:

```bash
.venv/bin/python object-ident.py --camera-index 1 --duration 20
```

Para executar sem janela:

```bash
.venv/bin/python object-ident.py --no-display --duration 20
```

Para uma imagem estática, sem abrir a câmera:

```bash
.venv/bin/python object-ident.py --image foto.jpg --image-output resultado.jpg
```

Nesse caso, `--image` e `--image-output` são usados juntos. O antigo
`--image foto.jpg --output resultado.jpg` continua aceito. O programa salva a imagem
com as anotações. Encerre o vídeo com `q`, `Esc`, fechando a janela ou `Ctrl+C`.

## Teste no computador com ESP32

### 1. Preparar e gravar a ESP32

Conecte o OLED ou os ESCs conforme a tabela de saída e escolha `--output oled`
ou `--output motors` no comando Python:
`true` para a tela, `false` para os motores. Conecte a ESP32 ao computador com
um cabo USB de dados. Liste as portas:

```bash
.venv/bin/python -m serial.tools.list_ports
```

Compile e grave o perfil **USB**, substituindo a porta pelo dispositivo listado:

```bash
pio run --project-dir firmware/ControleESP32 --environment esp32-usb
pio run --project-dir firmware/ControleESP32 --environment esp32-usb --target upload --upload-port /dev/ttyUSB0
```

Na Arduino IDE, use `ECO_SERIAL_USB=1` antes de gravar. No Windows, a porta de
gravação e execução pode ser, por exemplo, `COM3`.

### 2. Executar o reconhecimento com a comunicação

Feche o monitor serial da Arduino IDE ou do PlatformIO, conecte a webcam ao
computador e execute:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0
```

O programa consulta a placa, solicita parada, envia `CONFIG:OLED:0` por padrão,
exige `CONFIG_OK:OLED:0`, espera `READY` e confirma outra parada. A preparação
da saída leva cerca de três segundos. No OLED padrão, a ESP32 informa
`INICIAR:1` e libera o reconhecimento continuamente, sem sensor e sem limite
de 30 s. Isso vale para USB e UART2; é preciso gravar o firmware atualizado.
Com `--ultrasonic`, só recebe essa liberação após o disparo.
A câmera continua aberta e a janela mostra as linhas e a parada enquanto
espera. Não é necessário reiniciar o Python a cada disparo do sensor.

### 3. Conferir o comportamento

No teste OLED padrão, apresente um alvo configurado à esquerda, no meio e à direita:
os comandos esperados são `d`, `w` e `a`. Faça o centro da caixa
alcançar a linha horizontal: o comando deve virar `s`. O ponto verde marca esse
centro; somente a ponta da caixa cruzar a linha não deve parar. Retire o alvo e
confira a parada. Se houver mais
de uma garrafa, o alvo destacado deve permanecer acompanhado sem trocar apenas
porque outra caixa ficou maior.

As classes de `ssd_mobilenet.detection_types` também são usadas pela navegação.
Para testar com celular, use `cell phone`. Depois de alcançar a faixa inferior,
retire o alvo por três inferências (cerca de 1 s) para liberar outro teste;
enquanto a mesma aproximação estiver encerrada, `s` permanece esperado.

Somente com sensor habilitado, dispare antes o HC-SR04 abaixo de 15 cm.
Ao terminar a janela, confira `INICIAR:0` e a parada, mesmo que ainda haja uma
garrafa na câmera. O firmware rejeita movimentos enquanto aguarda o sensor.
Sem eco válido, nenhuma janela deve começar. Para conferir o vencimento,
execute sem `--duration` ou use um tempo maior que 30 s e afaste o objeto do
sensor após o disparo. Se ele continuar abaixo de 15 cm, a próxima leitura
após o vencimento poderá abrir outra janela. Leituras próximas ou sem eco
durante uma janela não reiniciam nem encerram seu prazo.

O mesmo teste aceita `--no-display` e `--duration 20`. Para testar comandos
manualmente, sem a câmera, use o monitor serial descrito em [Comandos úteis](#comandos-úteis).

## Setup na Raspberry Pi 5 com ESP32

### 1. Instalar o projeto e a câmera

Para o teste com vídeo, use Raspberry Pi OS de 64 bits com Desktop. A instalação
abaixo parte dessa edição. Copie as fontes e os modelos **sem copiar `.venv/`**
e crie o ambiente na Pi. Ambientes virtuais são vinculados ao sistema onde foram
criados; prepare um novo `.venv` na Raspberry, conforme a
[documentação do Python](https://docs.python.org/3/library/venv.html).

No terminal da Pi, instale o suporte a venv e, na raiz do projeto, execute:

```bash
sudo apt update
sudo apt install -y python3-venv
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

Conecte a câmera USB à Pi. Primeiro confira apenas o reconhecimento:

```bash
.venv/bin/python object-ident.py --duration 20
```

Em SSH ou console sem sessão gráfica, acrescente `--no-display`. O Raspberry
Pi OS Lite também exige esse argumento e pode precisar das bibliotecas nativas
do OpenCV que a edição Desktop já fornece; a receita acima não valida sua
instalação no Lite. Ajuste `--camera-index` se a webcam não for o índice zero.

### 2. Preparar a ESP32 e ligar a UART

Escolha `--output oled` para a tela ou `--output motors` para os motores no Python.
Grave o perfil
**UART2** pelo cabo USB da ESP32, usando o computador de programação ou a Pi:

```bash
pio run --project-dir firmware/ControleESP32 --environment esp32 --target upload --upload-port /dev/ttyUSB0
```

Na Arduino IDE, use `ECO_SERIAL_USB=0`. A porta USB acima serve para gravar;
a comunicação da Pi em operação usa a UART dos GPIOs.

| Raspberry Pi 5 | ESP32-WROOM-32 |
|---|---|
| GPIO 14 / TX, pino físico 8 | RX2 / GPIO 16 |
| GPIO 15 / RX, pino físico 10 | TX2 / GPIO 17 |
| GND, por exemplo pino físico 6 | GND |

Na ESP32, os GPIOs 16/17 costumam estar identificados como RX2/TX2 na placa.
Cruze TX com RX e compartilhe GND. Use sinais UART TTL de **3,3 V**. A numeração
GPIO e a posição física do conector são diferentes. Os pinos da Pi podem ser
conferidos no [mapa do conector](https://gpiozero.readthedocs.io/en/stable/cli_pinout.html),
e a configuração RX/TX da ESP32 na
[API UART](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html).
O fio de retorno ESP32→Pi é necessário para as confirmações.

A alimentação da ESP32 pode vir de sua conexão USB, enquanto a comunicação
com a Pi passa pelos fios UART. A câmera permanece conectada à Pi. O OLED ou
os ESCs ficam conectados à ESP32 conforme a seção de saída.

### 3. Habilitar a UART dos GPIOs da Pi 5

Abra:

```bash
sudo raspi-config
```

Em **Interface Options → Serial Port**, responda **No** para o login/console
serial e **Yes** para habilitar o hardware serial. Edite
`/boot/firmware/config.txt`:

```bash
sudo nano /boot/firmware/config.txt
```

Em uma seção ativa para a Pi 5, como `[all]`, adicione a linha abaixo se ainda
não estiver presente. Ela habilita a UART nos GPIOs 14/15:

```ini
dtoverlay=uart0-pi5
```

Reinicie e confira a porta:

```bash
sudo reboot
```

Depois de reconectar:

```bash
ls -l /dev/ttyAMA0
readlink -f /dev/serial0
```

Use `/dev/ttyAMA0` para a ligação deste guia e confirme sua presença. Na Pi 5,
`/dev/serial0` pode apontar para `/dev/ttyAMA10`, no conector de depuração.
A configuração e os dispositivos estão descritos na
[documentação de UART da Raspberry](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-uarts)
e no [overlay oficial uart0-pi5](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README).

Se a porta pertencer ao grupo `dialout` e ocorrer erro de permissão:

```bash
sudo usermod -a -G dialout "$USER"
```

Faça novo login para aplicar o grupo.

### 4. Confirmar a ligação e executar

Antes da câmera com comandos, consulte a ESP32 e confirme somente a parada:

```bash
.venv/bin/python - <<'PY'
from esp32_link import Esp32Link

link = Esp32Link('/dev/ttyAMA0')
try:
    print('ESP32 pronta; parada inicial confirmada.')
finally:
    link.close()
PY
```

Depois execute com vídeo:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0
```

Ou headless, adequado ao acesso SSH:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0 --no-display
```

Confira a sequência `d → w → a → s`, a parada ao perder o alvo e o timeout.
No OLED padrão, não há disparo do sensor nem limite de 30 s. Quando
sensor habilitado por `--ultrasonic` ou pelo padrão de `motors`, dispare primeiro
o HC-SR04 abaixo de 15 cm e confira
`INICIAR:0` e a parada ao completar 30 s. Para testar só a câmera, execute
sem `--serial-port`.
Para os motores, acrescente `--output motors` ao comando; para a tela, use
`--output oled` ou mantenha o padrão. A preparação completa também está no
[guia físico](TESTE_FISICO_RPI5.md).

## Configuração do reconhecimento

Edite [config.json](../config.json) e reinicie o programa para aplicar as mudanças.

| Parâmetro | Valor atual | Efeito |
|---|---|---|
| `camera.device_index` | `0` | Índice da webcam |
| `camera.width` / `height` | `640` / `480` | Resolução solicitada |
| `camera.fps` | `30` | Limite de entrega de frames à aplicação |
| `ssd_mobilenet.confidence_threshold` | `0.45` | Confiança mínima |
| `ssd_mobilenet.input_width` / `input_height` | `320` / `320` | Entrada da rede |
| `ssd_mobilenet.detection_types` | `["bottle", "cell phone"]` | Classes reconhecidas e usadas para navegação |
| `detection_interval_ms` | `300` | Intervalo mínimo entre inferências |
| `image_processing.enabled` | `true` | Redução proporcional quando necessária |
| `image_processing.max_width` / `max_height` | `640` / `480` | Limites antes da entrada da rede |
| `display.bottom_zone_ratio` | `0.8` | Linha horizontal em 80% da altura |
| `navigation.horizontal_hysteresis_ratio` | `0.03` | Margem de troca de região |
| `navigation.target_max_distance_px` | `90` | Distância máxima para associação por centro |
| `navigation.target_min_iou` | `0.1` | Sobreposição mínima para associação |
| `navigation.target_missing_frames` | `3` | Inferências ausentes para liberar o alvo |

FPS e inferência são controles separados: o perfil entrega até 30 frames por
segundo e permite aproximadamente 3,3 inferências por segundo, conforme o tempo
de processamento. Na Pi, meça esse tempo antes de ajustar os valores. As decisões
precisam chegar com margem abaixo do watchdog de três segundos para manter o
movimento. A captura real pode ter FPS diferente do valor solicitado; o software
limita a entrega mesmo quando a webcam ignora o pedido.

Os caminhos do modelo são relativos ao JSON:

```text
models/frozen_inference_graph.pb
models/ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt
models/coco.names
```

`coco.names` usa um nome por linha, com o ID definido pela posição. A origem e
os hashes dos modelos estão em [models/origem.json](../models/origem.json).
`display` configura a linha inferior; a janela é controlada pelo comando.

## Comandos úteis

### Reconhecimento e diagnóstico

```bash
# Ver argumentos
.venv/bin/python object-ident.py --help

# Usar outro perfil e outra câmera
.venv/bin/python object-ident.py --config config.json --camera-index 1

# ESP32 por USB, sem janela, durante 20 segundos
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0 --no-display --duration 20

# Usar outro arquivo de log
.venv/bin/python object-ident.py --log-file logs/teste.jsonl

# Listar portas e conferir dependências
.venv/bin/python -m serial.tools.list_ports
.venv/bin/python -m pip check

# Ativar o ambiente; depois, python aponta para o venv
source .venv/bin/activate
```

`--display` solicita explicitamente o vídeo, que já é o padrão. O modo de
imagem estática usa `--image` com `--image-output` (ou o antigo `--output`) e
não aceita `--serial-port`.

### Monitor serial e comandos manuais

Com o perfil USB gravado, feche o reconhecimento e abra:

```bash
.venv/bin/python -m serial.tools.miniterm /dev/ttyUSB0 115200 --eol LF
```

Na Pi com o perfil UART2, substitua a porta por `/dev/ttyAMA0`. A placa anuncia
`CONFIG_REQUIRED` ao ligar. Envie `CONFIG:OLED:0` para OLED contínuo,
`CONFIG:OLED:1` para OLED com sensor, `CONFIG:MOTORES:1` para motores com sensor
ou `CONFIG:MOTORES:0` para motores sem sensor. Aguarde a confirmação exata
`CONFIG_OK:<saida>:<sensor>` e depois `READY`. Envie `?` para consultar o estado.
Somente com sensor habilitado, dispare o HC-SR04 antes de enviar movimentos.
Envie `a`, `w`, `d` ou `s`,
sempre com Enter. `Ctrl+]` fecha o miniterm; envie `s` antes de sair.
O monitor serial da Arduino IDE também pode ser usado com **115200 baud** e
**nova linha** no perfil USB. Use um programa por vez na mesma porta.

| Mensagem | Função |
|---|---|
| `?` | Consulta prontidão e `INICIAR:0/1`; aplica parada |
| `CONFIG_REQUIRED` | Placa aguardando configuração, sem saída inicializada |
| `CONFIG:OLED:0/1` | Configura OLED sem/com sensor |
| `CONFIG:MOTORES:0/1` | Configura motores sem/com sensor |
| `CONFIG_OK:<saida>:<sensor>` | Confirmação exata do modo aplicado; depois aguarde `READY` |
| `ARMING` / `READY` | Inicialização em andamento / firmware pronto |
| `a`, `w`, `d`, `s` | Movimentos e parada |
| `CMD_OK:<comando>` | Confirmação de aceitação |
| `CAPS:HEARTBEAT` | Anúncio de suporte ao heartbeat |
| `h` / `HB_OK` | Renovação do timeout sem mudar o movimento |
| `TIMEOUT:s` | Parada após três segundos sem mensagens de movimento/heartbeat |
| `ERROR:<motivo>` | Erro informado pelo firmware |
| `INICIAR:1` / `INICIAR:0` | Liberado / aguardando o sensor; sem ultrassônico, a liberação é contínua |

Com ultrassônico habilitado e fora da janela, `a/w/d` provocam parada e resposta `INICIAR:0`, sem `CMD_OK`
para o movimento. `s` e `h` continuam aceitos quando a placa está pronta;
`h` não libera movimentos. Firmware antigo sem suporte a `CONFIG` é rejeitado
pelo Python; grave a versão atual antes de usar os novos argumentos.

Quando habilitado, o HC-SR04 é lido a cada 100 ms, com `pulseIn` limitado a 30 ms. Uma distância
válida abaixo de 15 cm libera a janela. A ESP32 encerra os movimentos
localmente após 30 s; `h` não prolonga essa autorização. `INICIAR:1/0` são
mensagens enviadas pela ESP32, não comandos manuais para forçar a liberação.

A configuração é mantida apenas em RAM e reaplicada pelo Python a cada execução.
Para trocar o modo, encerre o programa e inicie novamente com os argumentos desejados.

O Python espera até oito segundos por `READY` e um segundo por confirmação.
Suprime movimentos repetidos e envia `h` no máximo uma vez por segundo, quando
uma decisão recente mantém o comando. A renovação depende da câmera e da
inferência; ela não roda em uma thread independente. Para este teste, grave o
firmware atualizado, que informa a liberação contínua ou pelo HC-SR04.

Falhas de comunicação solicitam `s` e encerram a execução. Quando a serial está
totalmente indisponível, o watchdog da ESP32 aplica a parada. Comandos inválidos
também param os motores. No modo manual, sem novas mensagens, a parada ocorre
após três segundos.

### Compilação e testes de software

```bash
# Compilar UART2 sem gravar
pio run --project-dir firmware/ControleESP32 --environment esp32

# Compilar USB sem gravar
pio run --project-dir firmware/ControleESP32 --environment esp32-usb

# Executar testes sem câmera, serial ou motores físicos
.venv/bin/python -B -m unittest discover -s tests -v
```

O firmware usa 50 Hz, resolução de 16 bits e pulsos de 1000–2000 µs. A potência
inicial é 30% por ESC, com alvo de 1300 µs. O armamento leva três segundos e a
rampa muda 15 µs a cada 20 ms. `POTENCIA_ESC1` e `POTENCIA_ESC2` ajustam os alvos;
a configuração JSON ajusta o reconhecimento.

### Problemas comuns

| Sintoma | Verificação |
|---|---|
| Janela não abre | Sessão gráfica disponível e OpenCV com GUI; em SSH, use `--no-display` |
| Câmera não abre | Conexão USB, permissões e `camera.device_index` / `--camera-index` |
| ESP32 não confirma `READY` | Porta correta, perfil USB/UART2, RX/TX cruzados e GND comum |
| Acesso negado à serial | Grupo da porta e outro programa usando o dispositivo |
| OLED não mostra texto | `--output oled`, confirmação `CONFIG_OK`, alimentação, SDA=23, SCL=22 e endereço `0x3C` |
| Motores não acionam | `--output motors`, confirmação `CONFIG_OK`, sensor quando habilitado, alimentação dos ESCs e pinagem |
| Paradas por timeout | Tempo real de inferência e chegada de mensagens abaixo de três segundos |
| Serial pronta, mas sem reconhecimento/movimento | Firmware atualizado, argumentos de sensor e `INICIAR:1`; para teste sem sensor, use `--output oled --no-ultrasonic` |
| Sem confirmação `CONFIG_OK` | Grave o novo firmware e confira se outro programa ocupa a porta |
| Celular aparece na imagem, mas só há `s` | `cell phone` em `detection_types`, programa atualizado, centro da caixa acima da faixa inferior e aproximação anterior já liberada |

GPIO 12 participa da configuração de boot da ESP32. Se a placa deixar de
inicializar com o ESC conectado, confira o nível imposto a esse pino, conforme
o [datasheet do ESP32](https://documentation.espressif.com/esp32_datasheet_en.html).

### Timeout ao aguardar READY

Se `Esp32Link('/dev/ttyAMA0')` abrir a porta, mas não receber `READY` em oito
segundos, confira o canal usado pela ligação:

- **Raspberry por RX2/TX2:** grave o perfil `esp32`, com o padrão
  `ECO_SERIAL_USB=0`. O perfil `esp32-usb` recebe pelo cabo USB.
- **Cabo USB:** use o perfil `esp32-usb` e a porta USB identificada por
  `serial.tools.list_ports`, como `/dev/ttyUSB0` ou `/dev/ttyACM0`.
- **UART dos GPIOs:** confira o overlay `uart0-pi5`, a porta `/dev/ttyAMA0`,
  TX da Pi → RX2 da ESP32, RX da Pi ← TX2 da ESP32 e GND comum.

Com o reconhecimento fechado, consulte a porta manualmente:

```bash
.venv/bin/python -m serial.tools.miniterm /dev/ttyAMA0 115200 --eol LF
```

Envie `?` e pressione Enter. O firmware responde `CAPS:HEARTBEAT`, `INICIAR:0/1`
e `CONFIG_REQUIRED` se ainda não estiver configurado. Envie `CONFIG:OLED:0`,
aguarde `CONFIG_OK:OLED:0` e depois `READY`. Se já configurado, a consulta retorna
`READY` quando está pronto ou `ARMING` durante a preparação. Sem resposta,
confira firmware, porta, ligação e alimentação. Se aparecer `ERROR:OLED`,
a inicialização da tela falhou. Feche o monitor com `Ctrl+]` antes de repetir
o teste com `Esp32Link`.

## Logs e acompanhamento

Cada inferência aparece no terminal:

```text
timestamp: 2026-10-12-15-30
regiao: esquerda
objeto: bottle
garrafas_detectadas: 1
comando: d
```

O timestamp usa `AAAA-MM-DD-HH-SS`, sem minutos, no fuso de São Paulo, conforme
o formato solicitado. Sem alvo, a região é `sem_alvo` e o objeto é `nenhum`.
`garrafas_detectadas` conta somente as detecções `bottle`; um celular não incrementa
esse campo. `comando` mostra a decisão
mantida, inclusive quando um reenvio é suprimido ou substituído por heartbeat.

O arquivo `logs/recognition.jsonl` guarda dados completos: timestamp UTC, sequência,
evento, caixa, centro, confiança, `ymax`, estado da aproximação e modo de execução.
Inicialização da câmera, serial e erros também ficam nesse arquivo. A rotação
usa aproximadamente 2 MB por arquivo e conserva três arquivos anteriores.

```bash
tail -f logs/recognition.jsonl
```

## Validação e próximos passos

A revisão de software passou com **38 testes**, incluindo FPS, regiões, alvo,
histerese, parada persistente, logs, serial com falhas, watchdog e firmware OLED
sem PWM. Os perfis UART2 e USB compilaram para ESP32 Dev Module. A inferência
com o SSD real e a geração de uma imagem com divisórias também foram verificadas.
Os testes nativos cobrem as APIs Arduino-ESP32 2.x e 3.x.

A resposta física da tela, os ESCs, os motores e o desempenho na Raspberry ainda
precisam ser avaliados. O acompanhamento usa geometria e pode ficar ambíguo com
garrafas sobrepostas ou cruzando trajetórias. A precisão do detector ainda não
foi medida em um conjunto de imagens rotuladas.

Próximas etapas, em ordem de execução:

1. **Validar o OLED pelo computador.** Conferir `d/w/a/s`, confirmação serial,
   parada ao perder a garrafa e timeout, antes de acionar motores.
2. **Validar a Raspberry com OLED.** Medir FPS entregue, tempo de inferência e
   intervalo entre decisões; ajustar a configuração à câmera e à Pi.
3. **Validar os ESCs e motores em bancada.** Conferir armamento, pulso mínimo,
   potência, rampa e correspondência entre esquerda/direita com a montagem.
4. **Calibrar a navegação na embarcação.** Ajustar margem de histerese, linha
   inferior e potência a partir da trajetória observada e da posição da rede.
5. **Avaliar a detecção.** Registrar cenas de água com diferentes iluminações,
   reflexos, distâncias e oclusões; medir precisão e perdas antes de decidir
   por ajustes de confiança ou substituição/treinamento do modelo.
6. **Avaliar a coleta e a parada física.** Testar a aproximação com a rede e
   definir uma forma independente de confirmar coleta, caso a contagem seja
   necessária. A região inferior continua sendo apenas um indicativo visual.

Guias e registros adicionais:

- [Teste OLED](TESTE_OLED.md).
- [Montagem Raspberry Pi 5 e ESP32](TESTE_FISICO_RPI5.md).
- [Revisão da aproximação autônoma](REVISAO_AUTONOMIA.md).
- [Relatório da sessão](RELATORIO_SESSAO_2026-10-12.md).
- [Migração do V4.1 para a raiz](MIGRACAO_PARA_RAIZ.md).

`.venv/`, `.venv-anterior/`, `logs/`, `__pycache__/` e `.pio/` são arquivos gerados
localmente e ignorados pelo Git. Os documentos antigos da raiz estão preservados
em `docs/historico-raiz/`.
