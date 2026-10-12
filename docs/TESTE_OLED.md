# Teste dos comandos com OLED

No arquivo `firmware/ControleESP32/ControleESP32.ino`:

```cpp
constexpr bool OLED_TEST = true;
```

`true` exibe os comandos no OLED, sem configurar nem escrever PWM para os ESCs.
`false` usa o controle dos motores existente. Compile e grave novamente depois
de mudar essa constante. Não há comandos adicionais de ativação nem opção
especial no programa Python.

## Ligação

OLED SSD1306 de 128×64, endereço I2C `0x3C`:

| OLED | ESP32-WROOM-32 |
|---|---|
| SDA | GPIO 21 |
| SCL | GPIO 22 |
| GND | GND |
| VCC | 3,3 V, com módulo compatível com essa alimentação |

A ligação UART com a Raspberry está no [guia físico](TESTE_FISICO_RPI5.md).

## Gravação e execução

Use o perfil UART2 existente:

```bash
pio run --project-dir firmware/ControleESP32 --environment esp32 --target upload --upload-port /dev/ttyUSB0
```

A porta USB acima é usada para gravar. Na Raspberry, inicie o reconhecimento
pela UART dos GPIOs:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyAMA0
```

Para enviar comandos pelo USB da ESP32, grave com o perfil `esp32-usb` e use
`--serial-port /dev/ttyUSB0`. Na Arduino IDE, essa seleção continua sendo
`ECO_SERIAL_USB = 1` para USB ou `0` para UART2.

O PlatformIO instala Adafruit SSD1306, Adafruit GFX Library e Adafruit BusIO.
Na Arduino IDE, instale Adafruit SSD1306 e Adafruit GFX Library pelo gerenciador,
aceitando suas dependências. `Wire` acompanha o core Arduino-ESP32.

## O que aparece na tela

| Comando | Interpretação |
|---|---|
| `w` | Ambos: avançar |
| `a` | Motor esquerdo: virar à direita |
| `d` | Motor direito: virar à esquerda |
| `s` | Parado |

O monitor serial da Arduino IDE também pode enviar `a`, `w`, `d` ou `s`,
com nova linha, em 115200 baud, quando o firmware usa USB. Aguarde `READY`.
O protocolo, as confirmações e a parada por timeout de três segundos continuam
iguais. Heartbeats mantêm o comando exibido; não substituem a letra na tela.

A tela atualiza ao receber um comando de movimento ou de parada, incluindo a
parada pelo watchdog. O modo OLED não executa a rampa dos motores. A tela mostra
o estado interpretado pela ESP32. A implementação foi validada por testes e
compilação; a tela física ainda precisa ser conferida.
