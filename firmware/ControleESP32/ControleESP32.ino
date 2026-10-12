#include <Arduino.h>
#include <esp_arduino_version.h>

// 0: UART2 para a Raspberry Pi; 1: UART0/USB para testes de bancada.
#ifndef ECO_SERIAL_USB
#define ECO_SERIAL_USB 0
#endif

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// true: exibe os comandos no OLED; false: controla os motores.
constexpr bool OLED_TEST = true;
Adafruit_SSD1306 display(128, 64, &Wire, -1);

#if ECO_SERIAL_USB
auto& SerialComando = Serial;
#else
auto& SerialComando = Serial2;
#endif

constexpr uint8_t UART_RX_PIN = 16;
constexpr uint8_t UART_TX_PIN = 17;

constexpr uint8_t ESC_PIN1 = 12;
constexpr uint8_t ESC_PIN2 = 14;
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr int ESC_MIN_US = 1000;
constexpr int ESC_MAX_US = 2000;
constexpr int POTENCIA_ESC1 = 30;
constexpr int POTENCIA_ESC2 = 30;
constexpr uint32_t PWM_HZ = 50;
constexpr uint8_t PWM_BITS = 16;
constexpr uint32_t ARMAR_MS = 3000;
constexpr uint32_t SEM_COMANDO_MS = 3000;
constexpr uint32_t RAMPA_INTERVALO_MS = 20;
constexpr int RAMPA_PASSO_US = 15;

int atual1 = ESC_MIN_US;
int atual2 = ESC_MIN_US;
int alvo1 = ESC_MIN_US;
int alvo2 = ESC_MIN_US;
char comandoAtual = 's';
bool pwmPronto = false;
bool armado = false;
uint32_t inicio = 0;
uint32_t ultimoComando = 0;
uint32_t ultimaRampa = 0;

uint32_t pulsoParaDuty(int pulso) {
  pulso = constrain(pulso, ESC_MIN_US, ESC_MAX_US);
  return (static_cast<uint32_t>(pulso) * (1UL << PWM_BITS) + 10000) / 20000;
}

void mostrarComandoNoOLED(char comando) {
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(0, 16);
  display.print("CMD: ");
  display.println(comando);
  display.setTextSize(1);
  display.setCursor(0, 46);
  display.println(comando == 'w' ? "Ambos: avancar" :
                  comando == 'a' ? "Esquerdo: virar dir" :
                  comando == 'd' ? "Direito: virar esq" : "Parado");
  display.display();
}

void escreverEscs() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(ESC_PIN1, pulsoParaDuty(atual1));
  ledcWrite(ESC_PIN2, pulsoParaDuty(atual2));
#else
  ledcWrite(0, pulsoParaDuty(atual1));
  ledcWrite(1, pulsoParaDuty(atual2));
#endif
}

void parar() {
  comandoAtual = 's';
  atual1 = alvo1 = ESC_MIN_US;
  atual2 = alvo2 = ESC_MIN_US;
  if (OLED_TEST) {
    mostrarComandoNoOLED(comandoAtual);
  } else {
    escreverEscs();
  }
}

int potenciaParaPulso(int potencia) {
  return map(constrain(potencia, 0, 100), 0, 100, ESC_MIN_US, ESC_MAX_US);
}

void executarComando(char comando) {
  if (comando != 'a' && comando != 'w' && comando != 'd' && comando != 's') {
    parar();
    SerialComando.println("ERROR:COMANDO_INVALIDO");
    return;
  }
  if (!armado && comando != 's') {
    SerialComando.println("ERROR:ESC_ARMANDO");
    return;
  }
  ultimoComando = millis();
  comandoAtual = comando;
  if (comando == 's') {
    parar();
  } else if (OLED_TEST) {
    mostrarComandoNoOLED(comando);
  } else {
    // a: motor esquerdo; d: motor direito; w: ambos.
    alvo1 = (comando == 'a' || comando == 'w') ? potenciaParaPulso(POTENCIA_ESC1) : ESC_MIN_US;
    alvo2 = (comando == 'd' || comando == 'w') ? potenciaParaPulso(POTENCIA_ESC2) : ESC_MIN_US;
  }
  SerialComando.print("CMD_OK:");
  SerialComando.println(comando);
}

void lerComandos() {
  static char entrada = 0;
  static bool invalida = false;
  for (int lidos = 0; lidos < 64 && SerialComando.available() > 0; ++lidos) {
    char byte = static_cast<char>(SerialComando.read());
    if (byte == '\r') continue;
    if (byte == '\n') {
      if (invalida) {
        parar();
        SerialComando.println("ERROR:COMANDO_INVALIDO");
      } else if (entrada != 0) {
        if (entrada == '?') {
          parar();
          SerialComando.println("CAPS:HEARTBEAT");
          SerialComando.println(armado ? "READY" : "ARMING");
        } else if (entrada == 'h') {
          if (armado) {
            ultimoComando = millis();
            SerialComando.println("HB_OK");
          } else {
            SerialComando.println("ERROR:ESC_ARMANDO");
          }
        } else {
          executarComando(entrada);
        }
      }
      entrada = 0;
      invalida = false;
    } else if (entrada == 0) {
      entrada = byte;
    } else {
      invalida = true;
    }
  }
}

int aproximar(int atual, int alvo) {
  if (atual < alvo) return min(atual + RAMPA_PASSO_US, alvo);
  if (atual > alvo) return max(atual - RAMPA_PASSO_US, alvo);
  return atual;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
#if !ECO_SERIAL_USB
  SerialComando.begin(SERIAL_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  Serial.println("LINK:UART2 RX=16 TX=17 BAUD=115200");
#endif
  if (OLED_TEST) {
    Wire.begin(21, 22);
    pwmPronto = display.begin(SSD1306_SWITCHCAPVCC, 0x3C, true, false);
    if (!pwmPronto) {
      SerialComando.println("ERROR:OLED");
      return;
    }
    display.setTextColor(SSD1306_WHITE);
    display.setTextWrap(false);
  } else {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    bool primeiro = ledcAttach(ESC_PIN1, PWM_HZ, PWM_BITS);
    bool segundo = ledcAttach(ESC_PIN2, PWM_HZ, PWM_BITS);
    pwmPronto = primeiro && segundo;
#else
    double primeiro = ledcSetup(0, PWM_HZ, PWM_BITS);
    double segundo = ledcSetup(1, PWM_HZ, PWM_BITS);
    ledcAttachPin(ESC_PIN1, 0);
    ledcAttachPin(ESC_PIN2, 1);
    pwmPronto = primeiro > 0 && segundo > 0;
#endif
  }
  parar();
  if (!pwmPronto) {
    SerialComando.println("ERROR:PWM");
    return;
  }
  inicio = millis();
  ultimaRampa = inicio;
  SerialComando.println("ARMING");
}

void loop() {
  if (!pwmPronto) {
    delay(1);
    return;
  }
  uint32_t agora = millis();
  if (!armado && agora - inicio >= ARMAR_MS) {
    armado = true;
    ultimoComando = agora;
    SerialComando.println("READY");
  }
  lerComandos();
  agora = millis();
  if (armado && comandoAtual != 's' && agora - ultimoComando >= SEM_COMANDO_MS) {
    parar();
    SerialComando.println("TIMEOUT:s");
  }
  if (!OLED_TEST && armado && agora - ultimaRampa >= RAMPA_INTERVALO_MS) {
    ultimaRampa = agora;
    atual1 = aproximar(atual1, alvo1);
    atual2 = aproximar(atual2, alvo2);
    escreverEscs();
  }
}
