#include <cassert>
#include <iostream>
#include "ControleESP32.ino"

void send(const std::string& message) {
  for (char byte : message) Serial.input.push_back(byte);
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
  assert(testDuty[14] == pulsoParaDuty(second));
#else
  assert(testDuty[0] == pulsoParaDuty(first));
  assert(testDuty[1] == pulsoParaDuty(second));
#endif
}

int main() {
  setup();
  expectPulses(1000, 1000);
  send("a\n");
  assert(!armado && comandoAtual == 's');
  assert(Serial.output.find("ERROR:ESC_ARMANDO") != std::string::npos);
  send("h\n");
  assert(!armado && comandoAtual == 's');
  testClock += 3000;
  loop();
  assert(armado && Serial.output.find("READY") != std::string::npos);

  send("a\n");
  assert(comandoAtual == 'a');
  assert(atual1 < 1300);
  settle();
  expectPulses(1300, 1000);
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
  assert(Serial.output.find("HB_OK") != std::string::npos);
  testClock = ultimoComando + 2500;
  loop();
  expectPulses(1300, 1300);
  testClock = ultimoComando + 3000;
  loop();
  expectPulses(1000, 1000);
  assert(Serial.output.find("TIMEOUT:s") != std::string::npos);
  send("h\n");
  expectPulses(1000, 1000);
  assert(comandoAtual == 's');

  send("w\n");
  settle();
  send("?\n");
  assert(Serial.output.find("CAPS:HEARTBEAT") != std::string::npos);
  expectPulses(1000, 1000);
  send("w\n");
  settle();
  send("wa\n");
  expectPulses(1000, 1000);
  send("w\n");
  settle();
  send("x\n");
  expectPulses(1000, 1000);

  testClock = UINT32_MAX - 1000;
  send("w\n");
  settle();
  testClock += 2500;
  loop();
  expectPulses(1000, 1000);
  std::cout << "OK: comandos, rampa, parada, heartbeat e rollover; core "
            << TEST_CORE_VERSION << '\n';
}
