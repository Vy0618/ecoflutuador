# Teste físico — Raspberry Pi 5, ESP32-WROOM-32 e câmera USB

Preparação: 12/10/2026, 16:51:32, America/Sao_Paulo (UTC−03:00).

A Raspberry Pi 5 executa o SSD MobileNet e a navegação. A câmera USB se conecta
à Pi. O ESP32-WROOM-32 recebe os comandos pela UART2 e controla os ESCs.
O Python e a captura USB existentes são usados sem alteração.

Para conferir a interpretação antes de ter os motores, use o
[teste OLED](TESTE_OLED.md), com `--output oled` no Python. Para acionar os motores,
use `--output motors`; o sensor é habilitado por padrão. `--ultrasonic` e
`--no-ultrasonic` escolhem explicitamente o uso do HC-SR04. Grave o firmware
atualizado uma vez; a troca de modo passa pela UART, sem editar o sketch.

## Ligação

| Raspberry Pi 5 | ESP32-WROOM-32 |
|---|---|
| GPIO 14 / TX, pino físico 8 | GPIO 16 / RX da UART2 |
| GPIO 15 / RX, pino físico 10 | GPIO 17 / TX da UART2 |
| GND, por exemplo pino físico 6 | GND |

A numeração GPIO e a numeração física do conector da Pi são diferentes.
Na ESP32, 16 e 17 são números GPIO. A conexão cruza TX com RX e compartilha GND.
Os sinais são TTL de 3,3 V; não use sinais de 5 V ou RS-232 nesses GPIOs.
O retorno ESP32→Pi é necessário para `READY`, `CMD_OK` e `HB_OK`.

Os motores continuam na pinagem existente: ESC 1, motor esquerdo, GPIO 12;
ESC 2, motor direito, GPIO 14. Os ESCs usam sua alimentação própria e compartilham
a referência de GND com a ESP32. Os GPIOs fornecem apenas os sinais dos ESCs.

GPIO 12 também participa da configuração de boot do ESP32 clássico. Se a
conexão do ESC impedir a placa de iniciar, verifique se ele força esse pino
para nível alto durante o reset antes de atribuir a falha à UART. A função de
strapping está descrita no [datasheet do ESP32](https://documentation.espressif.com/esp32_datasheet_en.html).

## Firmware

O sketch principal usa UART2 a 115200 baud, 8N1, RX=16 e TX=17. Todos os comandos
e respostas passam por `SerialComando`, associado a `Serial2`. A UART0/USB fica
para programação. O firmware anuncia `CONFIG_REQUIRED` na UART selecionada e
aguarda a configuração enviada pelo Python antes de inicializar a saída.

Na Arduino IDE, abra `firmware/ControleESP32/ControleESP32.ino`, selecione ESP32
Dev Module e grave o sketch com `ECO_SERIAL_USB=0`, seu valor padrão.

Com PlatformIO, compile o perfil padrão:

```bash
pio run --project-dir firmware/ControleESP32 --environment esp32
```

Depois, para gravar uma placa conectada à porta correspondente:

```bash
pio run --project-dir firmware/ControleESP32 --environment esp32 --target upload --upload-port /dev/ttyUSB0
```

A porta acima é um exemplo no computador usado para gravação, não a UART dos
GPIOs da Pi. A gravação deve usar o perfil correto. Para conservar o teste
anterior com comandos pelo cabo USB, compile/grave `--environment esp32-usb`.
Na Arduino IDE, esse modo é selecionado com `ECO_SERIAL_USB=1`.

Há um único canal de controle por compilação: no modo UART2, comandos pela
UART0/USB não movem os motores. O protocolo `a/w/d/s`, a rampa, o heartbeat,
a parada imediata por `s` e o watchdog de três segundos permanecem iguais.

## Habilitar a UART dos GPIOs na Pi 5

No Raspberry Pi OS, use:

```bash
sudo raspi-config
```

Em Interfaces → Serial, desabilite o login/console serial e habilite o hardware
serial. Em `/boot/firmware/config.txt`, adicione, em uma seção ativa para a Pi 5
(por exemplo `[all]`), a linha abaixo se ela ainda não estiver presente:

```ini
dtoverlay=uart0-pi5
```

Esse overlay habilita a UART0 do RP1 nos GPIOs 14/15. Não habilite CTS/RTS para
esta ligação de três fios. Reinicie a Pi e confirme os dispositivos:

```bash
ls -l /dev/ttyAMA0
readlink -f /dev/serial0
```

Na Pi 5, `/dev/serial0` normalmente aponta para `/dev/ttyAMA10`, no conector de
depuração. A ligação deste guia usa a UART dos GPIOs 14/15, normalmente
`/dev/ttyAMA0`. Confirme a porta no sistema; não substitua automaticamente pelo
alias `/dev/serial0`. O console ou outro processo não pode ocupar essa porta.

Se houver erro de permissão, verifique o grupo mostrado por `ls -l`. Quando for
`dialout`, adicione o usuário a esse grupo e faça novo login:

```bash
sudo usermod -a -G dialout "$USER"
```

## Ambiente e câmera na Raspberry

Copie o projeto e crie um ambiente novo na Pi; não copie o `.venv` de um
computador x86. Na raiz do projeto:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

Conecte a câmera USB. O código usa OpenCV com V4L2 no Linux. Se ela não for a
primeira câmera, ajuste `camera.device_index` ou passe `--camera-index N`.
Os valores atuais de FPS, confiança, intervalo de inferência e linha de parada
continuam em `config.json`; ajuste-os conforme o desempenho medido na Pi.

Para verificar a câmera e as regiões sem acionar os motores:

```bash
.venv/bin/python object-ident.py
```

Sem sessão gráfica, use `--no-display`.

## Confirmar a comunicação antes da aproximação

Com o firmware UART2 gravado e a ligação pronta, esta verificação consulta o
ESP32 e confirma a parada, sem solicitar movimento:

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

O armamento leva três segundos. Uma falha de `READY` ou `CMD_OK:s` deve ser
resolvida na ligação, firmware, porta ou permissões antes do teste com motores.

## Operação e teste

Após confirmar câmera e comunicação, execute com vídeo:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0 --output motors
```

Ou sem janela:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0 --output motors --no-display
```

Para o teste sem motores, substitua `--output motors` por `--output oled`.
Com motores, o HC-SR04 libera a operação por 30 s após detectar menos de 15 cm;
confira a alimentação e a adaptação do ECHO no [guia de hardware](HARDWARE.md).
No primeiro ensaio de acionamento, remova as hélices. Apresente uma garrafa
nas regiões esquerda, centro e direita e confira os comandos `d`, `w`, `a` e
os motores correspondentes. Faça o centro da caixa atingir a linha e
confirme `s`. Retire o alvo e confira a parada. A ausência de mensagens recentes
deve resultar em parada pelo watchdog após três segundos.

O terminal mostra região, objeto, quantidade de detecções e comando de movimento.
A faixa inferior encerra a aproximação, sem confirmar coleta física. O teste
com hélices removidas verifica acionamentos; a trajetória e a coleta precisam
ser observadas na embarcação em operação.

## Evidências e referências

Nesta preparação, o firmware compilou para ESP32 nos perfis UART2 e USB. A
simulação C++ passou nas quatro combinações de core 2.x/3.x e UART2/USB,
incluindo pinagem, isolamento da porta de diagnóstico, comandos, rampa,
confirmações, heartbeat, watchdog e rollover. Não houve gravação de placa,
teste na Raspberry ou acionamento físico nesta execução.

- [API UART Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/serial.html).
- [Pinagem ESP32-DevKitC com módulo WROOM](https://docs.espressif.com/projects/esp-idf/en/v4.4.1/esp32/hw-reference/esp32/get-started-devkitc.html).
- [UART e console no Raspberry Pi OS](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-uarts).
- [Overlay oficial uart0-pi5](https://raw.githubusercontent.com/raspberrypi/firmware/master/boot/overlays/README).
- [Níveis elétricos dos GPIOs da Raspberry](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio).
