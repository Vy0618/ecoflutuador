#include <cassert>
#include <cmath>
#include <iostream>
#include "ControleESP32.ino"

void send(const std::string& message) {
  for (char byte : message) SerialComando.input.push_back(byte);
  loop();
}

void clearEchoes() {
  for (uint8_t pin : {21, 35, 32}) {
    testEchoDurations[pin] = 0;
    testEchoDelaysUs[pin] = 0;
    testEchoHeldHigh[pin] = false;
  }
}

void measure() {
  testClock += 100;
  const uint32_t before = micros();
  const uint32_t triggers = testTriggerCalls;
  loop();
  assert(testTriggerCalls == triggers + 1);
  assert(testTriggerWidthUs == 10 && testDigitalValues[19] == LOW);
  assert(micros() - before <= 30100);  // Um timeout total, mesmo com sensores ausentes.
}

void expectDistance(int sensor, float expected) {
  assert(std::fabs(distancias[sensor] - expected) < 0.02f);
}

int main() {
  testPerPinEcho = true;
  setup();
  assert(testPinModeCalls[19] == 1 && testPinModes[19] == OUTPUT);
  for (uint8_t pin : {21, 35, 32}) {
    assert(testPinModeCalls[pin] == 1 && testPinModes[pin] == INPUT);
  }
  for (int sensor = 1; sensor <= 3; ++sensor) {
    assert(display.shown.find("Dist" + std::to_string(sensor) + ": sem eco") != std::string::npos);
  }
  send("CONFIG:OLED:1\n");
  testClock = inicio + 3000;
  loop();
  assert(armado && !iniciar);

  // Os tres pulsos comecam juntos; o segundo e o terceiro terminam antes do primeiro.
  testEchoDurations[21] = 1800;
  testEchoDurations[35] = 700;
  testEchoDurations[32] = 1200;
  measure();
  expectDistance(0, 30.87f);
  expectDistance(1, 12.005f);
  expectDistance(2, 20.58f);
  assert(std::fabs(distancia - 12.005f) < 0.02f && iniciar);
  assert(display.shown.find("Dist1: 30.9 cm") != std::string::npos);
  assert(display.shown.find("Dist2: 12.0 cm") != std::string::npos);
  assert(display.shown.find("Dist3: 20.6 cm") != std::string::npos);

  // Cada ECHO, isoladamente, pode liberar uma janela sem depender dos outros.
  for (uint8_t pin : {21, 35, 32}) {
    clearEchoes();
    send("CONFIG:OLED:1\n");
    assert(!iniciar);
    testEchoDurations[pin] = 700;
    measure();
    assert(iniciar && inicioTimer == testClock);
    const uint32_t start = inicioTimer;
    measure();
    assert(inicioTimer == start);
    for (uint8_t sensor = 0; sensor < NUM_SENSORES; ++sensor) {
      if (echoPins[sensor] == pin) expectDistance(sensor, 12.005f);
      else assert(distancias[sensor] < 0);
    }
    clearEchoes();
    testClock = start + 30000;
    loop();
    assert(!iniciar && comandoAtual == 's');
  }

  // O limite continua estritamente abaixo de 15 cm, inclusive no terceiro ECHO.
  for (uint8_t pin : {21, 35, 32}) testEchoDurations[pin] = 875;
  measure();
  assert(!iniciar && distancia >= 15.0f);
  testEchoDurations[32] = 874;
  measure();
  assert(iniciar && distancia < 15.0f);

  // Pulsos sobrepostos com atrasos diferentes preservam a duracao de cada sensor.
  clearEchoes();
  testEchoDurations[21] = 2000;
  testEchoDurations[35] = 600;
  testEchoDurations[32] = 900;
  testEchoDelaysUs[35] = 300;
  testEchoDelaysUs[32] = 500;
  measure();
  expectDistance(0, 34.3f);
  expectDistance(1, 10.29f);
  expectDistance(2, 15.435f);

  // Sem novos ecos, nenhuma distancia anterior pode permanecer valida.
  clearEchoes();
  measure();
  assert(distancia < 0);
  for (float value : distancias) assert(value < 0);

  // ECHO preso em HIGH ou sem descida no prazo nao impede a leitura do GPIO32.
  testEchoHeldHigh[21] = true;
  testEchoDurations[35] = 40000;
  testEchoDurations[32] = 700;
  measure();
  assert(distancias[0] < 0 && distancias[1] < 0);
  expectDistance(2, 12.005f);
  assert(std::fabs(distancia - distancias[2]) < 0.02f);

  // Uma subida que so ocorre depois do timeout nao deve liberar a navegacao.
  clearEchoes();
  send("CONFIG:OLED:1\n");
  testEchoDurations[21] = 700;
  testEchoDelaysUs[21] = 31000;
  measure();
  assert(!iniciar && distancia < 0);

  // A medicao tambem funciona ao atravessar o rollover de micros().
  clearEchoes();
  testClock = UINT32_MAX / 1000u;
  testSubClockUs = UINT32_MAX % 1000u - 100u;
  ultimaLeitura = testClock - 100;
  testEchoDurations[21] = 700;
  testEchoDurations[35] = 800;
  testEchoDurations[32] = 900;
  const uint32_t beforeWrap = micros();
  loop();
  assert(micros() < beforeWrap);
  expectDistance(0, 12.005f);
  expectDistance(1, 13.72f);
  expectDistance(2, 15.435f);
  assert(iniciar && testPwmCalls == 0);
  std::cout << "OK: tres ECHOs, TRIG comum, sobreposicao, timeout e rollover\n";
}
