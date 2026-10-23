#include <cassert>
#include <iostream>
#include "ControleESP32.ino"

void send(const std::string& message) {
  for (char byte : message) SerialComando.input.push_back(byte);
  loop();
}

void expectScreen(char command, const std::string& action) {
  assert(display.shown.find(std::string("CMD: ") + command) != std::string::npos);
  assert(display.shown.find(action) != std::string::npos);
  assert(testPwmCalls == 0);
  assert(atual1 == 1000 && atual2 == 1000 && alvo1 == 1000 && alvo2 == 1000);
}

int main(int argc, char**) {
  if (argc > 1) display.initialize = false;
  setup();
  if (argc == 1) {
    expectScreen('s', "Dist: sem eco");
    testEchoDuration = 700;
    testClock += 100;
    loop();
    expectScreen('s', "Dist: 12.0 cm");
    assert(!saidaPronta && !iniciar);
    testEchoDuration = 0;
    testClock += 100;
    loop();
    expectScreen('s', "Dist: sem eco");
  }
  assert(testPwmCalls == 0);
  assert(!saidaPronta && !armado && !iniciar);
  send(TEST_ULTRASONIC ? "CONFIG:OLED:1\n" : "CONFIG:OLED:0\n");
  assert(Wire.sda == OLED_SDA && Wire.scl == OLED_SCL);
  if (argc > 1) {
    assert(!saidaPronta);
    assert(SerialComando.output.find("ERROR:OLED") != std::string::npos);
    testClock = 4000;
    send("w\n");
    assert(!armado && comandoAtual == 's' && testPwmCalls == 0);
    return 0;
  }
  assert(display.width == 128 && display.height == 64 && display.address == 0x3C);
  assert(!display.reinitializeWire);
  expectScreen('s', "Parado");
  testClock = inicio + 3000;
  loop();
  if (!usarUltrassonico) {
    assert(iniciar && armado);
    assert(testPinModeCalls[19] == 1 && testPinModeCalls[21] == 1);
    SerialComando.output.clear();
    send("?\n");
    assert(SerialComando.output == "CAPS:HEARTBEAT\nINICIAR:1\nREADY\n");
    for (uint32_t time : {3000u, 33000u, 93000u}) {
      testClock = time;
      testEchoDuration = 0;
      send("d\n");
      expectScreen('d', "Direito: virar esq");
      send("w\n");
      expectScreen('w', "Ambos: avancar");
      send("a\n");
      expectScreen('a', "Esquerdo: virar dir");
      assert(iniciar && testPulseCalls > 0);
      assert(display.shown.find("Dist: sem eco") != std::string::npos);
    }
    testEchoDuration = 700;
    testClock += 100;
    loop();
    expectScreen('a', "Dist: 12.0 cm");
    testEchoDuration = 0;
    testClock += 100;
    loop();
    expectScreen('a', "Dist: sem eco");
    assert(SerialComando.output.find("INICIAR:0") == std::string::npos);
    testClock = ultimoComando + 3000;
    loop();
    expectScreen('s', "Parado");
    assert(iniciar);
    assert(SerialComando.output.find("TIMEOUT:s") != std::string::npos);
    std::cout << "OK: OLED continuo sem sensor, sem PWM e com watchdog\n";
    return 0;
  }
  send("?\n");
  assert(SerialComando.output.find("CAPS:HEARTBEAT\nINICIAR:0\nREADY\n") != std::string::npos);
  SerialComando.output.clear();
  send("w\n");
  expectScreen('s', "Parado");
  assert(SerialComando.output == "INICIAR:0\n");
  testEchoDuration = 700;
  testClock += 100;
  loop();
  testEchoDuration = 0;
  assert(iniciar);
  expectScreen('s', "Dist: 12.0 cm");
  send("w\n");
  expectScreen('w', "Ambos: avancar");
  assert(SerialComando.output.find("CMD_OK:w") != std::string::npos);
  send("h\n");
  expectScreen('w', "Ambos: avancar");
  send("d\n");
  expectScreen('d', "Direito: virar esq");
  send("a\n");
  expectScreen('a', "Esquerdo: virar dir");
  send("s\n");
  expectScreen('s', "Parado");
  send("w\n");
  testClock = ultimoComando + 3000;
  loop();
  expectScreen('s', "Parado");
  assert(SerialComando.output.find("TIMEOUT:s") != std::string::npos);
  send("w\n");
  send("wa\n");
  expectScreen('s', "Parado");
  // Leituras proximas e comandos nao renovam os 30 segundos da janela.
  const uint32_t start = inicioTimer;
  testEchoDuration = 700;
  for (uint32_t elapsed : {10000u, 15000u, 20000u, 29000u}) {
    testClock = start + elapsed;
    send("w\nh\n");
    assert(iniciar && inicioTimer == start);
    expectScreen('w', "Ambos: avancar");
  }
  testClock = start + 30000;
  SerialComando.output.clear();
  send("w\n");
  assert(!iniciar && inicioTimer == start);
  expectScreen('s', "Parado");
  assert(SerialComando.output == "INICIAR:0\nINICIAR:0\n");
  testEchoDuration = 0;
  testClock += 100;
  loop();
  assert(!iniciar);
  testEchoDuration = 875;  // Aproximadamente 15,006 cm: nao e menor que 15.
  testClock += 100;
  loop();
  assert(!iniciar);
  testEchoDuration = 874;  // Aproximadamente 14,989 cm: abaixo do limite.
  testClock += 100;
  SerialComando.output.clear();
  loop();
  assert(iniciar && inicioTimer == testClock);
  assert(SerialComando.output == "INICIAR:1\n");
  // Mesmo com um objeto persistente, primeiro expira; so outra leitura reativa.
  testClock = inicioTimer + 30000;
  loop();
  assert(!iniciar);
  testClock += 100;
  loop();
  assert(iniciar && inicioTimer == testClock);
  // O tempo gasto em pulseIn tambem participa da expiracao.
  testEchoDuration = 0;
  testClock = inicioTimer + 29990;
  testPulseDelayMs = 30;
  send("w\n");
  assert(!iniciar);
  expectScreen('s', "Parado");
  testPulseDelayMs = 0;
  // Janela iniciada antes da volta do contador expira corretamente depois dela.
  testClock = UINT32_MAX - 1000;
  testEchoDuration = 700;
  loop();
  const uint32_t wrapStart = inicioTimer;
  assert(iniciar);
  testEchoDuration = 0;
  testClock = wrapStart + 29999;
  loop();
  assert(iniciar);
  testClock = wrapStart + 30000;
  send("a\nd\nw\n");
  assert(!iniciar);
  expectScreen('s', "Parado");
  std::cout << "OK: comandos no OLED, parada e nenhum PWM\n";
}
