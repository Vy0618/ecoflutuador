#include <cassert>
#include <iostream>
#include "ControleESP32.ino"

void send(const std::string& message) {
  for (char byte : message) SerialComando.input.push_back(byte);
  loop();
}

void settle() {
  for (int step = 0; step < 30; ++step) {
    testClock += 20;
    loop();
  }
}

void expectPulses(int first, int second) {
  assert(atual1 == first && atual2 == second);
#if TEST_CORE_VERSION >= 3
  assert(testDuty[12] == pulsoParaDuty(first));
  assert(testDuty[13] == pulsoParaDuty(second));
#else
  assert(testDuty[0] == pulsoParaDuty(first));
  assert(testDuty[1] == pulsoParaDuty(second));
#endif
}

int main() {
  setup();
  assert(!saidaPronta && !armado && !iniciar);
  send("CONFIG:MOTORES:1\n");
  assert(SerialComando.baud == 115200);
#if ECO_SERIAL_USB
  assert(&SerialComando == &Serial);
  assert(Serial2.baud == 0);
#else
  assert(&SerialComando == &Serial2);
  assert(SerialComando.config == SERIAL_8N1);
  assert(SerialComando.rxPin == 16 && SerialComando.txPin == 17);
  // A porta de diagnostico nao pode introduzir outro controlador dos motores.
  Serial.input.push_back('w');
  Serial.input.push_back('\n');
#endif
  expectPulses(1000, 1000);
  send("a\n");
  assert(!armado && comandoAtual == 's');
  assert(SerialComando.output.find("ERROR:ESC_ARMANDO") != std::string::npos);
  send("h\n");
  assert(!armado && comandoAtual == 's');
  testClock += 3000;
  loop();
  assert(armado && SerialComando.output.find("READY") != std::string::npos);
  assert(comandoAtual == 's');
  assert(!iniciar);
  assert(testPinModeCalls[19] == 1 && testPinModes[19] == OUTPUT);
  assert(testPinModeCalls[21] == 1 && testPinModes[21] == INPUT);
  SerialComando.output.clear();
  send("?\n");
  assert(SerialComando.output == "CAPS:HEARTBEAT\nINICIAR:0\nREADY\n");
  for (const char command : {'a', 'w', 'd'}) {
    SerialComando.output.clear();
    send(std::string(1, command) + "\n");
    expectPulses(1000, 1000);
    assert(SerialComando.output == "INICIAR:0\n");
  }
  testEchoDuration = 700;
  testClock += 100;
  loop();
  testEchoDuration = 0;
  assert(iniciar);
  assert(testTriggerCalls > 0 && testTriggerWidthUs == 10);
  assert(testDigitalValues[19] == LOW);
  SerialComando.output.clear();
  send("?\n");
  assert(SerialComando.output == "CAPS:HEARTBEAT\nINICIAR:1\nREADY\n");

  send("a\n");
  assert(comandoAtual == 'a');
  assert(atual1 < 1300);
  settle();
  expectPulses(1300, 1000);
  const uint32_t stablePwmCalls = testPwmCalls;
  testClock += 100;
  loop();
  expectPulses(1300, 1000);
  assert(testPwmCalls == stablePwmCalls);
  send("w\r\n");
  settle();
  expectPulses(1300, 1300);
  send("d\n");
  settle();
  expectPulses(1000, 1300);
  send("s\n");
  expectPulses(1000, 1000);

  send("w\n");
  settle();
  testClock = ultimoComando + 2500;
  send("h\n");
  assert(comandoAtual == 'w');
  assert(alvo1 == 1300 && alvo2 == 1300);
  assert(SerialComando.output.find("HB_OK") != std::string::npos);
  testClock = ultimoComando + 2500;
  loop();
  expectPulses(1300, 1300);
  testClock = ultimoComando + 3000;
  loop();
  expectPulses(1000, 1000);
  assert(SerialComando.output.find("TIMEOUT:s") != std::string::npos);
  send("h\n");
  expectPulses(1000, 1000);
  assert(comandoAtual == 's');

  send("w\n");
  settle();
  send("?\n");
  assert(SerialComando.output.find("CAPS:HEARTBEAT") != std::string::npos);
  expectPulses(1000, 1000);
  send("w\n");
  settle();
  send("wa\n");
  expectPulses(1000, 1000);
  send("w\n");
  settle();
  send("x\n");
  expectPulses(1000, 1000);

  // A nova janela comeca perto do rollover; expiracao usa subtracao uint32_t.
  testClock = UINT32_MAX - 1000;
  loop();
  assert(!iniciar);
  testEchoDuration = 700;
  testClock += 100;
  loop();
  testEchoDuration = 0;
  assert(iniciar);
  send("w\n");
  settle();
  testClock += 2500;
  loop();
  expectPulses(1000, 1000);
  // Fim da janela desliga ESCs mesmo com movimento recente na fila.
  testClock = inicioTimer + 29000;
  send("w\n");
  settle();
  expectPulses(1300, 1300);
  testClock = inicioTimer + 30000;
  SerialComando.output.clear();
  send("a\nd\nw\n");
  assert(!iniciar && comandoAtual == 's');
  expectPulses(1000, 1000);
  assert(SerialComando.output == "INICIAR:0\nINICIAR:0\nINICIAR:0\nINICIAR:0\n");
  std::cout << "OK: comandos, rampa, parada, heartbeat e rollover; core "
            << TEST_CORE_VERSION << '\n';
}
