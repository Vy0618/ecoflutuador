# Teste dos comandos com OLED

O modo é escolhido ao iniciar o Python, sem editar variáveis do firmware:

```bash
# OLED continuo, sem sensor (padrao)
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0 --output oled

# OLED com ativacao pelo HC-SR04 durante 30 s
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0 --output oled --ultrasonic
```

**Grave o firmware atualizado uma vez.** Depois, os argumentos configuram a saída
e o sensor pela UART a cada execução. `--output oled` usa a tela, sem gerar PWM;
`--output motors` usa os ESCs e habilita o sensor por padrão. `--ultrasonic` e
`--no-ultrasonic` sobrescrevem esse padrão. `--no-display` desliga apenas a janela
de vídeo do computador, sem desligar o OLED.

A ESP32 inicia com `CONFIG_REQUIRED`. O Python solicita parada, envia
`CONFIG:OLED:0`, confere `CONFIG_OK:OLED:0`, aguarda `READY` e confirma outra
parada antes do reconhecimento. Sem sensor, recebe `INICIAR:1`; com sensor, aguarda
o disparo. A tela já mostra comando e distância ao ligar, antes da configuração.

## Ligação

OLED SSD1306 de 128×64, endereço I2C `0x3C`:

| OLED | ESP32-WROOM-32 |
|---|---|
| SDA | GPIO 23 (`OLED_SDA`, valor atual do firmware) |
| SCL | GPIO 22 |
| GND | GND |
| VCC | 3,3 V, com módulo compatível com essa alimentação |

A ligação UART com a Raspberry está no [guia físico](TESTE_FISICO_RPI5.md).
O HC-SR04 não precisa estar conectado no teste contínuo: nesse caso aparece
`Dist: sem eco`. Quando conectado, a medição usa TRIG19 e ECHO21 em todos os
modos, com adaptação do ECHO de 5 V para 3,3 V.
Confira a alimentação e as ligações no [guia de hardware](HARDWARE.md#hc-sr04-ligações-previstas).

## Gravação e execução

Use o perfil UART2 existente:

```bash
.venv/bin/pio run --project-dir firmware/ControleESP32 --environment esp32 --target upload --upload-port /dev/ttyUSB0
```

A porta USB acima é usada para gravar. Na Raspberry, inicie o reconhecimento
pela UART dos GPIOs:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0 --output oled
```

Para testar no computador pelo cabo USB:

```bash
.venv/bin/pio run --project-dir firmware/ControleESP32 --environment esp32-usb --target upload --upload-port /dev/ttyUSB0
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0 --output oled
```

Feche o monitor serial antes de executar o Python. Na Arduino IDE, a seleção é
`ECO_SERIAL_USB = 1` para USB ou `0` para UART2.

O PlatformIO instala Adafruit SSD1306, Adafruit GFX Library e Adafruit BusIO.
Na Arduino IDE, instale Adafruit SSD1306 e Adafruit GFX Library pelo gerenciador,
aceitando suas dependências. `Wire` acompanha o core Arduino-ESP32.

No padrão OLED sem sensor, o reconhecimento começa após `READY` e a parada
inicial, sem limite de 30 segundos. O watchdog de comunicação continua ativo.
Se acrescentar `--ultrasonic`, o comportamento volta à janela de 30 s
após uma distância válida abaixo de 15 cm.

## Alvo usado no teste

As classes em `ssd_mobilenet.detection_types`, no `config.json`, são usadas
tanto para detectar quanto para decidir os comandos. Para celular, use o nome
COCO **`cell phone`**; `smartphone` não existe nessa lista.

Com o centro da caixa do celular acima da faixa inferior, mova-o entre esquerda,
meio e direita: os comandos devem ser `d`, `w` e `a`. O ponto verde marca o centro.
A ponta da caixa pode entrar na faixa inferior sem parar; quando o centro entra, o comando
passa a `s` e a aproximação fica encerrada. Para repetir, retire o celular do
quadro até desaparecer por três inferências (cerca de 1 s com a configuração
atual) e apresente-o novamente. Sem alvo válido, `s` é o comportamento esperado.

## O que aparece na tela

A mensagem padrão aparece nos modos `oled` e `motors`:

```text
CMD: w
Dist: 12.0 cm
Ambos: avancar
```

A distância é atualizada a cada leitura, mesmo sem trocar o comando.
Sem eco válido, aparece `Dist: sem eco`. O sensor é lido também com
`--no-ultrasonic`; a opção dispensa somente sua função de liberar a operação.
O teste continua funcionando sem o sensor conectado, mostrando `sem eco`.

| Comando | Interpretação |
|---|---|
| `w` | Ambos: avançar |
| `a` | Motor esquerdo: virar à direita |
| `d` | Motor direito: virar à esquerda |
| `s` | Parado |

O monitor serial da Arduino IDE também pode enviar `a`, `w`, `d` ou `s`,
com nova linha, em 115200 baud, quando o firmware usa USB. Envie primeiro
`CONFIG:OLED:0` e aguarde `CONFIG_OK:OLED:0` e `READY`; depois teste `a/w/d/s`.
Não precisa disparar o HC-SR04 nesse modo. Para trocar a configuração, pare
com `s` antes; um pedido durante movimento é rejeitado e também aplica parada.
As confirmações e a parada por timeout de três segundos continuam funcionando.
Heartbeats mantêm o comando exibido; quando o sensor está habilitado, não
prolongam a janela de 30 segundos.

A tela atualiza ao medir a distância e ao receber um comando de movimento ou de
parada, incluindo a parada pelo watchdog. O modo OLED não executa a rampa dos motores. A tela mostra
o estado interpretado pela ESP32. A implementação foi validada por testes e
compilação; a tela física ainda precisa ser conferida.
