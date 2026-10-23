#include <Arduino.h>
#include <esp_arduino_version.h>
#include <string.h>

// 0: UART2 para a Raspberry Pi; 1: UART0/USB para testes de bancada.
#ifndef ECO_SERIAL_USB
#define ECO_SERIAL_USB 0
#endif

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// Recebidos por CONFIG:OLED:0/1 ou CONFIG:MOTORES:0/1, antes dos movimentos.
bool usarOled = true;
bool usarUltrassonico = false;
bool oledPronto = false;
float distancia = -1.0f;
Adafruit_SSD1306 display(128, 64, &Wire, -1);

#if ECO_SERIAL_USB
auto& SerialComando = Serial;
#else
auto& SerialComando = Serial2;
#endif

constexpr uint8_t UART_RX_PIN = 16;
constexpr uint8_t UART_TX_PIN = 17;
const int trigPin = 19;
const int echoPin = 21;
constexpr int OLED_SDA = 23;
constexpr int OLED_SCL = 22;
const unsigned long tempoAtivacao = 30000;
bool iniciar = false;
uint32_t inicioTimer = 0;
uint32_t ultimaLeitura = 0;

constexpr uint8_t ESC_PIN1 = 12;
constexpr uint8_t ESC_PIN2 = 13;
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
bool saidaPronta = false;
bool armado = false;
uint32_t inicio = 0;
uint32_t ultimoComando = 0;
uint32_t ultimaRampa = 0;

uint32_t pulsoParaDuty(int pulso) {
  pulso = constrain(pulso, ESC_MIN_US, ESC_MAX_US);
  return (static_cast<uint32_t>(pulso) * (1UL << PWM_BITS) + 10000) / 20000;
}

void mostrarComandoNoOLED(char comando) {
  if (!oledPronto) return;
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(0, 4);
  display.print("CMD: ");
  display.println(comando);
  display.setTextSize(1);
  display.setCursor(0, 32);
  display.print("Dist: ");
  if (distancia >= 0) {
    display.print(distancia, 1);
    display.println(" cm");
  } else {
    display.println("sem eco");
  }
  display.setCursor(0, 52);
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

void desativarPWM() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcDetach(ESC_PIN1);
  ledcDetach(ESC_PIN2);
#else
  ledcDetachPin(ESC_PIN1);
  ledcDetachPin(ESC_PIN2);
#endif
  pinMode(ESC_PIN1, OUTPUT);
  pinMode(ESC_PIN2, OUTPUT);
  digitalWrite(ESC_PIN1, LOW);
  digitalWrite(ESC_PIN2, LOW);
}

void parar() {
  comandoAtual = 's';
  atual1 = alvo1 = ESC_MIN_US;
  atual2 = alvo2 = ESC_MIN_US;
  if (saidaPronta && !usarOled) {
    escreverEscs();
  }
  mostrarComandoNoOLED(comandoAtual);
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
  if (!iniciar && comando != 's') {
    parar();
    SerialComando.write("INICIAR:0\n");
    return;
  }
  ultimoComando = millis();
  comandoAtual = comando;
  if (comando == 's') {
    parar();
  } else {
    if (!usarOled) {
      // a: motor esquerdo; d: motor direito; w: ambos.
      alvo1 = (comando == 'a' || comando == 'w') ? potenciaParaPulso(POTENCIA_ESC1) : ESC_MIN_US;
      alvo2 = (comando == 'd' || comando == 'w') ? potenciaParaPulso(POTENCIA_ESC2) : ESC_MIN_US;
    }
    mostrarComandoNoOLED(comando);
  }
  SerialComando.print("CMD_OK:");
  SerialComando.println(comando);
}

void configurarSaida(bool oled, bool ultrassonico);

void lerComandos() {
  static char entrada[24];
  static uint8_t tamanho = 0;
  static bool invalida = false;
  for (int lidos = 0; lidos < 64 && SerialComando.available() > 0; ++lidos) {
    char byte = static_cast<char>(SerialComando.read());
    if (byte == '\r') continue;
    if (byte == '\n') {
      entrada[tamanho] = '\0';
      if (invalida) {
        parar();
        SerialComando.println("ERROR:COMANDO_INVALIDO");
      } else if (strncmp(entrada, "CONFIG:", 7) == 0) {
        if (strcmp(entrada, "CONFIG:OLED:0") != 0 && strcmp(entrada, "CONFIG:OLED:1") != 0 &&
            strcmp(entrada, "CONFIG:MOTORES:0") != 0 && strcmp(entrada, "CONFIG:MOTORES:1") != 0) {
          parar();
          SerialComando.write("ERROR:CONFIG_INVALIDA\n");
        } else if (comandoAtual != 's') {
          parar();
          SerialComando.write("ERROR:CONFIG_EM_MOVIMENTO\n");
        } else {
          configurarSaida(entrada[7] == 'O', entrada[tamanho - 1] == '1');
          if (saidaPronta) {
            SerialComando.write("CONFIG_OK:");
            SerialComando.write(entrada + 7);
            SerialComando.write("\n");
            SerialComando.write(iniciar ? "INICIAR:1\n" : "INICIAR:0\n");
            SerialComando.write("ARMING\n");
          }
        }
      } else if (tamanho == 1) {
        if (entrada[0] == '?') {
          parar();
          SerialComando.println("CAPS:HEARTBEAT");
          SerialComando.write(iniciar ? "INICIAR:1\n" : "INICIAR:0\n");
          SerialComando.write(!saidaPronta ? "CONFIG_REQUIRED\n" : armado ? "READY\n" : "ARMING\n");
        } else if (entrada[0] == 'h') {
          if (armado) {
            ultimoComando = millis();
            SerialComando.println("HB_OK");
          } else {
            SerialComando.println("ERROR:ESC_ARMANDO");
          }
        } else {
          executarComando(entrada[0]);
        }
      } else if (tamanho != 0) {
        parar();
        SerialComando.println("ERROR:COMANDO_INVALIDO");
      }
      tamanho = 0;
      invalida = false;
    } else if (byte != '\0' && tamanho < sizeof(entrada) - 1 && !invalida) {
      entrada[tamanho++] = byte;
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

void configurarSaida(bool oled, bool ultrassonico) {
  parar();
  if (saidaPronta && !usarOled) {
    desativarPWM();
  }
  saidaPronta = false;
  armado = false;
  iniciar = false;
  usarOled = oled;
  usarUltrassonico = ultrassonico;
  if (usarOled) {
    saidaPronta = oledPronto;
    if (!saidaPronta) {
      SerialComando.println("ERROR:OLED");
      return;
    }
  } else {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    bool primeiro = ledcAttach(ESC_PIN1, PWM_HZ, PWM_BITS);
    bool segundo = ledcAttach(ESC_PIN2, PWM_HZ, PWM_BITS);
    saidaPronta = primeiro && segundo;
#else
    double primeiro = ledcSetup(0, PWM_HZ, PWM_BITS);
    double segundo = ledcSetup(1, PWM_HZ, PWM_BITS);
    ledcAttachPin(ESC_PIN1, 0);
    ledcAttachPin(ESC_PIN2, 1);
    saidaPronta = primeiro > 0 && segundo > 0;
#endif
  }
  if (!saidaPronta) {
    desativarPWM();
    SerialComando.println("ERROR:PWM");
    return;
  }
  parar();
  inicio = millis();
  ultimaRampa = inicio;
  ultimaLeitura = inicio;
  inicioTimer = 0;
  iniciar = !usarUltrassonico;
}

void setup() {
  Serial.begin(SERIAL_BAUD);
#if !ECO_SERIAL_USB
  SerialComando.begin(SERIAL_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
#endif
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  digitalWrite(trigPin, LOW);
  Wire.begin(OLED_SDA, OLED_SCL);
  oledPronto = display.begin(SSD1306_SWITCHCAPVCC, 0x3C, true, false);
  if (oledPronto) {
    display.setTextColor(SSD1306_WHITE);
    display.setTextWrap(false);
    mostrarComandoNoOLED(comandoAtual);
  }
  SerialComando.write("CONFIG_REQUIRED\n");
}

void loop() {
  uint32_t agora = millis();
  if (saidaPronta && !armado && agora - inicio >= ARMAR_MS) {
    armado = true;
    ultimoComando = agora;
    SerialComando.println("READY");
  }
  // Mede em todos os modos; usarUltrassonico controla somente a ativacao.
  if (agora - ultimaLeitura >= 100) {
    ultimaLeitura = agora;
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);
    unsigned long duracao = pulseIn(echoPin, HIGH, 30000UL);
    distancia = duracao > 0 ? duracao * 0.0343f / 2.0f : -1.0f;
    mostrarComandoNoOLED(comandoAtual);
    if (usarUltrassonico && saidaPronta && !iniciar && duracao > 0 && distancia < 15.0f) {
      iniciar = true;
      inicioTimer = millis();
      SerialComando.write("INICIAR:1\n");
    }
  }
  if (usarUltrassonico && iniciar && millis() - inicioTimer >= tempoAtivacao) {
    iniciar = false;
    parar();
    SerialComando.write("INICIAR:0\n");
  }
  lerComandos();
  agora = millis();
  if (armado && comandoAtual != 's' && agora - ultimoComando >= SEM_COMANDO_MS) {
    parar();
    SerialComando.println("TIMEOUT:s");
  }
  if (!usarOled && armado && (atual1 != alvo1 || atual2 != alvo2) &&
      agora - ultimaRampa >= RAMPA_INTERVALO_MS) {
    ultimaRampa = agora;
    atual1 = aproximar(atual1, alvo1);
    atual2 = aproximar(atual2, alvo2);
    escreverEscs();
  }
}
