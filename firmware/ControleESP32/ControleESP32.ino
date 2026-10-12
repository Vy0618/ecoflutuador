#include <Arduino.h>
#include <esp_arduino_version.h>

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
  escreverEscs();
}

int potenciaParaPulso(int potencia) {
  return map(constrain(potencia, 0, 100), 0, 100, ESC_MIN_US, ESC_MAX_US);
}

void executarComando(char comando) {
  if (comando != 'a' && comando != 'w' && comando != 'd' && comando != 's') {
    parar();
    Serial.println("ERROR:COMANDO_INVALIDO");
    return;
  }
  if (!armado && comando != 's') {
    Serial.println("ERROR:ESC_ARMANDO");
    return;
  }
  ultimoComando = millis();
  comandoAtual = comando;
  // Acionamentos preservados de V3/ControleESP32.ino.
  switch (comando) {
    case 'a':
      alvo1 = potenciaParaPulso(POTENCIA_ESC1);
      alvo2 = ESC_MIN_US;
      break;
    case 'w':
      alvo1 = potenciaParaPulso(POTENCIA_ESC1);
      alvo2 = potenciaParaPulso(POTENCIA_ESC2);
      break;
    case 'd':
      alvo1 = ESC_MIN_US;
      alvo2 = potenciaParaPulso(POTENCIA_ESC2);
      break;
    case 's':
      parar();
      break;
  }
  Serial.print("CMD_OK:");
  Serial.println(comando);
}

void lerComandos() {
  static char entrada = 0;
  static bool invalida = false;
  for (int lidos = 0; lidos < 64 && Serial.available() > 0; ++lidos) {
    char byte = static_cast<char>(Serial.read());
    if (byte == '\r') continue;
    if (byte == '\n') {
      if (invalida) {
        parar();
        Serial.println("ERROR:COMANDO_INVALIDO");
      } else if (entrada != 0) {
        if (entrada == '?') {
          parar();
          Serial.println("CAPS:HEARTBEAT");
          Serial.println(armado ? "READY" : "ARMING");
        } else if (entrada == 'h') {
          if (armado) {
            ultimoComando = millis();
            Serial.println("HB_OK");
          } else {
            Serial.println("ERROR:ESC_ARMANDO");
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
  parar();
  if (!pwmPronto) {
    Serial.println("ERROR:PWM");
    return;
  }
  inicio = millis();
  ultimaRampa = inicio;
  Serial.println("ARMING");
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
    Serial.println("READY");
  }
  lerComandos();
  agora = millis();
  if (armado && comandoAtual != 's' && agora - ultimoComando >= SEM_COMANDO_MS) {
    parar();
    Serial.println("TIMEOUT:s");
  }
  if (armado && agora - ultimaRampa >= RAMPA_INTERVALO_MS) {
    ultimaRampa = agora;
    atual1 = aproximar(atual1, alvo1);
    atual2 = aproximar(atual2, alvo2);
    escreverEscs();
  }
}
