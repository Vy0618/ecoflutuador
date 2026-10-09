#include <Arduino.h>
#include <ESP32Servo.h>
#include <TinyGPSPlus.h>
#include "sensors_v4.h"

// Ecoflutuador 4.0 - controle, sensores e telemetria
// Placa prevista: ESP32 DevKit / ESP32-WROOM-32

// Motores (mantidos da V3)
constexpr uint8_t ESC_PIN1 = 12;
constexpr uint8_t ESC_PIN2 = 14;

// UART dedicada para Raspberry Pi
constexpr uint8_t RPI_RX_PIN = 16;  // Raspberry TX -> ESP32 RX
constexpr uint8_t RPI_TX_PIN = 17;  // Raspberry RX <- ESP32 TX
constexpr uint32_t RPI_BAUD = 115200;

// UART dedicada para GPS GY-NEO6MV2
constexpr uint8_t GPS_RX_PIN = 27;  // GPS TX -> ESP32 RX
constexpr uint8_t GPS_TX_PIN = 26;  // Opcional: GPS RX <- ESP32 TX
constexpr uint32_t GPS_BAUD = 9600;

// Sensores ambientais e START (ADC1 para coexistir com Wi-Fi)
constexpr uint8_t PH_PIN = 34;
constexpr uint8_t TURBIDITY_PIN = 35;
constexpr uint8_t ULTRASONIC_TRIG_PIN = 33;
constexpr uint8_t ULTRASONIC_ECHO_PIN = 32;
constexpr uint8_t NET_SENSOR_PIN = 25;
constexpr bool ENABLE_ULTRASONIC = true;
constexpr bool ENABLE_NET = true;
constexpr uint8_t NET_ACTIVE_LEVEL = LOW;
constexpr uint32_t ULTRASONIC_INTERVAL_MS = 100;
constexpr uint32_t ULTRASONIC_TIMEOUT_US = 25000;
constexpr uint32_t ULTRASONIC_TRIGGER_US = 10;
constexpr uint32_t ULTRASONIC_SETTLE_US = 2;
constexpr float SOUND_CM_PER_US = 0.0343f;
constexpr UltrasonicConfig ULTRASONIC_CONFIG = {
  2.0f, 400.0f,  // minimum / maximum valid distance (cm)
  15.0f, 10.0f,  // activation / release delta (cm)
  0.005f,        // free-water baseline adaptation alpha
  30, 3, 5       // calibration medians / START confirmations / clear medians
};
constexpr NetConfig NET_CONFIG = {50, 8000, 5000}; // debounce / full / free (ms)
constexpr uint32_t ESC_ARM_MS = 3000;
#ifndef ECO_ENABLE_MOTORS
#define ECO_ENABLE_MOTORS 0
#endif
constexpr bool ENABLE_MOTORS = ECO_ENABLE_MOTORS != 0;
UltrasonicSensor ultrasonic(ULTRASONIC_CONFIG);
NetSensor netSensor(NET_CONFIG);
uint32_t lastUltrasonic = 0;

// Ative somente depois de conectar e validar eletricamente cada sensor.
constexpr bool ENABLE_GPS = false;
constexpr bool ENABLE_PH = false;
constexpr bool ENABLE_TURBIDITY = false;
constexpr bool ENABLE_START_SENSOR = ENABLE_ULTRASONIC;

// Mantenha false ate calibrar com solucoes/referencias conhecidas.
constexpr bool PH_CALIBRATED = false;
constexpr float PH_SLOPE = -5.70f;
constexpr float PH_INTERCEPT = 21.34f;
constexpr bool TURBIDITY_CALIBRATED = false;
constexpr float TURBIDITY_SLOPE = 1.0f;
constexpr float TURBIDITY_INTERCEPT = 0.0f;

// Razao = tensao no sensor / tensao no ADC. Ajuste se houver divisor.
constexpr float PH_VOLTAGE_RATIO = 1.0f;
constexpr float TURBIDITY_VOLTAGE_RATIO = 1.0f;

constexpr uint32_t MOTOR_UPDATE_MS = 20;
constexpr uint32_t ANALOG_SAMPLE_MS = 100;
constexpr uint32_t TELEMETRY_INTERVAL_MS = 1000;
constexpr int MOTOR_STEP_US = 15;
constexpr size_t MAX_COMMAND_LENGTH = 32;
constexpr bool MIRROR_TELEMETRY_TO_USB = true;

Servo esc1;
Servo esc2;
HardwareSerial RaspberrySerial(2);
HardwareSerial GpsSerial(1);
TinyGPSPlus gps;

int potencia1 = 30;
int potencia2 = 30;
int micro1Atual = 1000;
int micro2Atual = 1000;
int micro1Alvo = 1000;
int micro2Alvo = 1000;

uint16_t phRaw = 0;
uint16_t turbidityRaw = 0;
uint16_t phMilliVolts = 0;
uint16_t turbidityMilliVolts = 0;
bool turbidityDigital = false;
bool startDetected = false;

uint32_t lastMotorUpdate = 0;
uint32_t lastAnalogSample = 0;
uint32_t lastTelemetry = 0;

CommandFramer rpiBuffer;
CommandFramer usbBuffer;
constexpr uint32_t CONTROL_TIMEOUT_MS = 1500;
constexpr char FIRMWARE_VERSION[] = "4.1.0";
ControlLease controlLease(CONTROL_TIMEOUT_MS);

int pctParaMicro(int pct) {
  pct = constrain(pct, 0, 100);
  return map(pct, 0, 100, 1000, 2000);
}

int aproximar(int atual, int alvo, int passo) {
  if (atual < alvo) return min(atual + passo, alvo);
  if (atual > alvo) return max(atual - passo, alvo);
  return atual;
}

void definirAlvos(int alvo1, int alvo2) {
  micro1Alvo = constrain(alvo1, 1000, 2000);
  micro2Alvo = constrain(alvo2, 1000, 2000);
}

void atualizarMotores() {
  const uint32_t now = millis();
  if (now - lastMotorUpdate < MOTOR_UPDATE_MS) return;
  lastMotorUpdate = now;

  micro1Atual = aproximar(micro1Atual, micro1Alvo, MOTOR_STEP_US);
  micro2Atual = aproximar(micro2Atual, micro2Alvo, MOTOR_STEP_US);
  if (!ENABLE_MOTORS || now < ESC_ARM_MS) return;
  esc1.writeMicroseconds(micro1Atual);
  esc2.writeMicroseconds(micro2Atual);
}

void parar() {
  definirAlvos(1000, 1000);
  micro1Atual = micro2Atual = 1000;
  controlLease.stop();
  if (ENABLE_MOTORS) {
    esc1.writeMicroseconds(1000);
    esc2.writeMicroseconds(1000);
  }
}

void avancar() {
  // Mapeamento preservado do ControleESP32.ino original.
  definirAlvos(pctParaMicro(potencia2), pctParaMicro(potencia1));
}

void esquerda() {
  definirAlvos(pctParaMicro(potencia2), 1000);
}

void direita() {
  definirAlvos(1000, pctParaMicro(potencia1));
}

void girarEsq() {
  definirAlvos(1000, pctParaMicro(potencia1));
}

void girarDir() {
  definirAlvos(pctParaMicro(potencia2), 1000);
}

void responder(Print &output, const String &message) {
  output.println(message);
  if (&output != &Serial) {
    Serial.print("RPI <- ");
    Serial.println(message);
  }
}

bool executarComando(char cmd) {
  if ((!ENABLE_MOTORS || millis() < ESC_ARM_MS ||
       (ENABLE_ULTRASONIC && (!ultrasonic.valid || !ultrasonic.calibrated))) && cmd != 's') return false;
  switch (cmd) {
    case 'w': avancar(); break;
    case 'a': esquerda(); break;
    case 'd': direita(); break;
    case 'q': girarEsq(); break;
    case 'e': girarDir(); break;
    case 's': parar(); break;
    default: return false;
  }
  controlLease.command(cmd, millis());
  return true;
}

void enviarTelemetria(Print &output);

void processarLinha(const String &receivedLine, Print &output) {
  String line = receivedLine;
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("HB:") && line.length() == 4) {
    if (controlLease.renew(line[3], millis())) responder(output, "HB_OK");
    else { parar(); responder(output, "ERR:CONTROL_LEASE"); }
    return;
  }

  if (line == "PING") {
    responder(output, "PONG");
    return;
  }

  if (line == "STATUS?") {
    enviarTelemetria(output);
    return;
  }

  if (line.startsWith("P") && line.length() == 5) {
    for (uint8_t i = 1; i < 5; ++i) {
      if (!isDigit(line[i])) {
        responder(output, "ERR:INVALID_POWER");
        return;
      }
    }
    const int motor = line.substring(1, 2).toInt();
    const int value = line.substring(2).toInt();
    if ((motor != 1 && motor != 2) || value < 0 || value > 100) {
      responder(output, "ERR:INVALID_POWER");
      return;
    }

    if (motor == 1) potencia1 = value;
    else potencia2 = value;
    responder(output, "PWR_OK:" + String(motor) + ":" + String(value));
    return;
  }

  if (line.length() == 1 && executarComando(line[0])) {
    responder(output, "CMD_OK:" + line);
    return;
  }

  responder(output, "ERR:INVALID_COMMAND");
}

void receberLinhas(Stream &input, Print &output, CommandFramer &buffer) {
  // Bound work per loop so serial noise cannot starve the control lease.
  for (unsigned n=0; n<128 && input.available()>0; ++n) {
    const auto result=buffer.feed(static_cast<char>(input.read()));
    if (result == CommandFramer::LINE) processarLinha(String(buffer.data), output);
    else if (result == CommandFramer::OVERFLOW) {
      parar();
      responder(output, "ERR:LINE_TOO_LONG");
    }
  }
}

uint16_t lerMediaADC(uint8_t pin) {
  constexpr uint8_t samples = 8;
  uint32_t sum = 0;
  for (uint8_t i = 0; i < samples; ++i) sum += analogRead(pin);
  return static_cast<uint16_t>(sum / samples);
}

uint16_t lerMediaMilliVolts(uint8_t pin) {
  constexpr uint8_t samples = 8;
  uint32_t sum = 0;
  for (uint8_t i = 0; i < samples; ++i) sum += analogReadMilliVolts(pin);
  return static_cast<uint16_t>(sum / samples);
}

void processarGPS() {
  if (!ENABLE_GPS) return;
  for (unsigned n=0; n<128 && GpsSerial.available()>0; ++n) gps.encode(GpsSerial.read());
}

void atualizarSensoresAnalogicos() {
  const uint32_t now = millis();
  if (now - lastAnalogSample < ANALOG_SAMPLE_MS) return;
  lastAnalogSample = now;

  if (ENABLE_PH) {
    phRaw = lerMediaADC(PH_PIN);
    phMilliVolts = lerMediaMilliVolts(PH_PIN);
  }

  if (ENABLE_TURBIDITY) {
    turbidityRaw = lerMediaADC(TURBIDITY_PIN);
    turbidityMilliVolts = lerMediaMilliVolts(TURBIDITY_PIN);
  }

}

void atualizarSensorStart() {
  if (!ENABLE_ULTRASONIC) return;
  const uint32_t now = millis();
  if (now-lastUltrasonic < ULTRASONIC_INTERVAL_MS) return;
  lastUltrasonic=now;
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(ULTRASONIC_SETTLE_US);
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(ULTRASONIC_TRIGGER_US);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  // Strict bound: at most 25 ms, even when disconnected. No delay().
  const unsigned long duration = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, ULTRASONIC_TIMEOUT_US);
  const int edge=ultrasonic.update(duration*SOUND_CM_PER_US/2.0f);
  startDetected=ultrasonic.start;
  if (!ultrasonic.valid && controlLease.current != 's') {
    parar();
    RaspberrySerial.println("ERR:ULTRASONIC_INVALID");
  }
  if (edge) RaspberrySerial.println(edge>0 ? "EVENT:START:1" : "EVENT:START:0");
}

void atualizarRede() {
  if (!ENABLE_NET) return;
  const unsigned events=netSensor.update(digitalRead(NET_SENSOR_PIN)==NET_ACTIVE_LEVEL, millis());
  if (events & NetSensor::BLOCKED) RaspberrySerial.println("EVENT:NET:BLOCKED");
  if (events & NetSensor::PASS) RaspberrySerial.println("EVENT:NET:PASS");
  if (events & NetSensor::FULL) RaspberrySerial.println("EVENT:NET:FULL_SUSPECTED");
  if (events & NetSensor::CLEAR) RaspberrySerial.println("EVENT:NET:CLEAR");
}

void imprimirNumeroOuNull(Print &output, bool valid, double value, uint8_t decimals) {
  if (valid) output.print(value, decimals);
  else output.print("null");
}

void enviarTelemetria(Print &output) {
  output.print("TEL:{\"schema\":1,\"uptime_ms\":");
  output.print(millis());
  output.print(",\"firmware_version\":\""); output.print(FIRMWARE_VERSION);
  output.print("\",\"protocol_version\":\"1.1\",\"control_timeout_ms\":");
  output.print(CONTROL_TIMEOUT_MS);

  output.print(",\"start\":{\"enabled\":");
  output.print(ENABLE_START_SENSOR ? "true" : "false");
  output.print(",\"detected\":");
  output.print(startDetected ? "true" : "false");
  output.print("}");

  output.print(",\"ultrasonic\":{\"enabled\":");
  output.print(ENABLE_ULTRASONIC ? "true" : "false");
  output.print(",\"valid\":"); output.print(ultrasonic.valid ? "true" : "false");
  output.print(",\"distance_cm\":"); imprimirNumeroOuNull(output, ultrasonic.valid, ultrasonic.distance, 2);
  output.print(",\"baseline_cm\":"); imprimirNumeroOuNull(output, ultrasonic.calibrated, ultrasonic.baseline, 2);
  output.print(",\"delta_cm\":"); imprimirNumeroOuNull(output, ultrasonic.valid && ultrasonic.calibrated, ultrasonic.delta, 2);
  output.print(",\"calibrated\":"); output.print(ultrasonic.calibrated ? "true" : "false");
  output.print(",\"start_detected\":"); output.print(startDetected ? "true" : "false");
  output.print(",\"state\":\""); output.print(ultrasonic.calibrated ? "READY" : "CALIBRATING");
  output.print("\"},\"net\":{\"enabled\":"); output.print(ENABLE_NET ? "true" : "false");
  output.print(",\"blocked\":"); output.print(netSensor.blocked ? "true" : "false");
  output.print(",\"blocked_ms\":"); output.print(netSensor.blockedMs(millis()));
  output.print(",\"passage_count\":"); output.print(netSensor.passageCount);
  output.print(",\"full_suspected\":"); output.print(netSensor.fullSuspected ? "true" : "false");
  output.print("}");

  const bool gpsValid = ENABLE_GPS && gps.location.isValid() && gps.location.age() < 5000;
  output.print(",\"gps\":{\"enabled\":");
  output.print(ENABLE_GPS ? "true" : "false");
  output.print(",\"valid\":");
  output.print(gpsValid ? "true" : "false");
  output.print(",\"lat\":");
  imprimirNumeroOuNull(output, gpsValid, gps.location.lat(), 6);
  output.print(",\"lon\":");
  imprimirNumeroOuNull(output, gpsValid, gps.location.lng(), 6);
  output.print(",\"altitude_m\":");
  imprimirNumeroOuNull(output, gpsValid && gps.altitude.isValid(), gps.altitude.meters(), 1);
  output.print(",\"speed_kmh\":");
  imprimirNumeroOuNull(output, gpsValid && gps.speed.isValid(), gps.speed.kmph(), 1);
  output.print(",\"satellites\":");
  if (ENABLE_GPS && gps.satellites.isValid()) output.print(gps.satellites.value());
  else output.print("null");
  output.print("}");

  const float phVoltage = (phMilliVolts / 1000.0f) * PH_VOLTAGE_RATIO;
  const float phValue = PH_SLOPE * phVoltage + PH_INTERCEPT;
  output.print(",\"water\":{\"ph_enabled\":");
  output.print(ENABLE_PH ? "true" : "false");
  output.print(",\"ph_raw\":");
  if (ENABLE_PH) output.print(phRaw); else output.print("null");
  output.print(",\"ph_voltage_v\":");
  imprimirNumeroOuNull(output, ENABLE_PH, phVoltage, 3);
  output.print(",\"ph\":");
  imprimirNumeroOuNull(output, ENABLE_PH && PH_CALIBRATED, phValue, 2);

  const float turbidityVoltage = (turbidityMilliVolts / 1000.0f) * TURBIDITY_VOLTAGE_RATIO;
  const float ntuValue = TURBIDITY_SLOPE * turbidityVoltage + TURBIDITY_INTERCEPT;
  output.print(",\"turbidity_enabled\":");
  output.print(ENABLE_TURBIDITY ? "true" : "false");
  output.print(",\"turbidity_raw\":");
  if (ENABLE_TURBIDITY) output.print(turbidityRaw); else output.print("null");
  output.print(",\"turbidity_voltage_v\":");
  imprimirNumeroOuNull(output, ENABLE_TURBIDITY, turbidityVoltage, 3);
  output.print(",\"turbidity_ntu\":");
  imprimirNumeroOuNull(output, ENABLE_TURBIDITY && TURBIDITY_CALIBRATED, ntuValue, 1);
  output.print(",\"turbidity_digital\":");
  output.print("null");  // legacy field: GPIO 32 now belongs to HC-SR04
  output.print("}");

  output.print(",\"motors\":{\"power_1_pct\":");
  output.print(potencia1);
  output.print(",\"power_2_pct\":");
  output.print(potencia2);
  output.print(",\"esc_1_us\":");
  output.print(micro1Atual);
  output.print(",\"esc_2_us\":");
  output.print(micro2Atual);
  output.println("}}");
}

void enviarTelemetriaPeriodica() {
  const uint32_t now = millis();
  if (now - lastTelemetry < TELEMETRY_INTERVAL_MS) return;
  lastTelemetry = now;
  enviarTelemetria(RaspberrySerial);
  if (MIRROR_TELEMETRY_TO_USB) enviarTelemetria(Serial);
}

void setup() {
  Serial.begin(115200);
  RaspberrySerial.begin(RPI_BAUD, SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN);
  if (ENABLE_GPS) GpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  pinMode(NET_SENSOR_PIN, INPUT_PULLUP);
  analogReadResolution(12);

  if (ENABLE_MOTORS) {
    esc1.attach(ESC_PIN1, 1000, 2000);
    esc2.attach(ESC_PIN2, 1000, 2000);
    esc1.writeMicroseconds(1000);
    esc2.writeMicroseconds(1000);
  }
  Serial.println("BOOT:READY");
  RaspberrySerial.println("BOOT:READY");
}

void loop() {
  if (controlLease.expired(millis())) {
    parar();
    RaspberrySerial.println("ERR:CONTROL_TIMEOUT");
  }
  receberLinhas(RaspberrySerial, RaspberrySerial, rpiBuffer);
  receberLinhas(Serial, Serial, usbBuffer);  // permite teste pelo Monitor Serial
  processarGPS();
  atualizarSensorStart();
  atualizarRede();
  atualizarSensoresAnalogicos();
  atualizarMotores();
  enviarTelemetriaPeriodica();
}
