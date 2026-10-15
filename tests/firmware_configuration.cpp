#include <cassert>
#include <iostream>
#include "ControleESP32.ino"

void send(const std::string& message) {
  for (char byte : message) SerialComando.input.push_back(byte);
  loop();
}

int main() {
  setup();
  assert(!pwmPronto && !armado && !iniciar && testPwmCalls == 0);
  assert(SerialComando.output == "CONFIG_REQUIRED\n");
  send("w\n");
  assert(comandoAtual == 's' && testPwmCalls == 0);
  send("s\n");
  assert(SerialComando.output.find("CMD_OK:s") != std::string::npos);

  // Linhas invalidas, longas ou incompletas nao liberam as saidas.
  const std::string invalid[] = {"CONFIG:OLED:2\n", "CONFIG:OUTRO:0\n",
                                 "CONFIG:OLED:0EXTRA\n", std::string(40, 'x') + "\n"};
  for (const std::string& command : invalid) {
    send(command);
    assert(!pwmPronto && !armado && comandoAtual == 's');
  }
  send("CONFIG:OL");
  assert(!pwmPronto);
  SerialComando.output.clear();
  send("ED:0\r\n");
  assert(OLED_TEST && !USAR_ULTRASSONICO && pwmPronto && iniciar && !armado);
  assert(SerialComando.output == "CONFIG_OK:OLED:0\nINICIAR:1\nARMING\n");
  assert(Wire.sda == OLED_SDA && Wire.scl == OLED_SCL && testPwmCalls == 0);
  testClock = inicio + 3000;
  loop();
  send("w\n");
  assert(display.shown.find("CMD: w") != std::string::npos);
  assert(testPwmCalls == 0);

  // Um pedido durante movimento para e e rejeitado; a proxima execucao envia s antes.
  send("CONFIG:MOTORES:1\n");
  assert(OLED_TEST && comandoAtual == 's');
  assert(SerialComando.output.find("ERROR:CONFIG_EM_MOVIMENTO") != std::string::npos);
  send("CONFIG:MOTORES:1\n");
  assert(!OLED_TEST && USAR_ULTRASSONICO && pwmPronto && !armado && !iniciar);
  assert(SerialComando.output.find("CONFIG_OK:MOTORES:1") != std::string::npos);
  assert(atual1 == 1000 && atual2 == 1000);
  testClock = inicio + 3000;
  loop();
  send("w\n");
  assert(comandoAtual == 's' && !iniciar);
  testEchoDuration = 700;
  testClock += 100;
  loop();
  testEchoDuration = 0;
  assert(iniciar);
  send("w\n");
  assert(alvo1 == 1300 && alvo2 == 1300);

  send("s\nCONFIG:OLED:1\n");
  assert(OLED_TEST && USAR_ULTRASSONICO && !iniciar && !armado);
  assert(testDetachCalls == 2);
  assert(testDigitalValues[12] == LOW && testDigitalValues[14] == LOW);
  const uint32_t pwmCalls = testPwmCalls;
  testClock = inicio + 3000;
  loop();
  testEchoDuration = 700;
  testClock += 100;
  loop();
  send("a\n");
  assert(display.shown.find("CMD: a") != std::string::npos);
  assert(testPwmCalls == pwmCalls);

  send("s\nCONFIG:MOTORES:0\n");
  assert(!OLED_TEST && !USAR_ULTRASSONICO && iniciar && !armado);
  testEchoDuration = 0;
  testClock = inicio + 3000;
  loop();
  send("d\n");
  assert(alvo1 == 1000 && alvo2 == 1300);
  testClock = ultimoComando + 3000;
  loop();
  assert(atual1 == 1000 && atual2 == 1000 && comandoAtual == 's');
  std::cout << "OK: configuracao UART, quatro modos, parada e troca de saidas\n";
}
