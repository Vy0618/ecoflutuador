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
  assert(testPwmCalls == 0);
  assert(Wire.sda == 21 && Wire.scl == 22);
  if (argc > 1) {
    assert(!pwmPronto);
    assert(SerialComando.output.find("ERROR:OLED") != std::string::npos);
    testClock = 4000;
    send("w\n");
    assert(!armado && comandoAtual == 's' && testPwmCalls == 0);
    return 0;
  }
  assert(display.width == 128 && display.height == 64 && display.address == 0x3C);
  assert(!display.reinitializeWire);
  expectScreen('s', "Parado");
  testClock = 3000;
  loop();
  send("?\n");
  assert(SerialComando.output.find("CAPS:HEARTBEAT") != std::string::npos);
  assert(SerialComando.output.find("READY") != std::string::npos);
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
  std::cout << "OK: comandos no OLED, parada e nenhum PWM\n";
}
