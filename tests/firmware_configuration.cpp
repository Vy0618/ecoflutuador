#include <cassert>
#include <iostream>
#include "ControleESP32.ino"

void send(const std::string& message) {
  for (char byte : message) SerialComando.input.push_back(byte);
  loop();
}

int main(int argc, char**) {
  if (argc > 1) display.initialize = false;
  setup();
  if (argc > 1) {
    // Uma falha na tela nao deve impedir o controle dos motores.
    assert(!oledPronto);
    send("CONFIG:MOTORES:0\n");
    assert(saidaPronta && iniciar);
    testClock = inicio + 3000;
    loop();
    send("w\n");
    assert(alvo1 == 1300 && alvo2 == 1300);
    send("s\n");
    assert(atual1 == 1000 && atual2 == 1000);
    assert(SerialComando.output.find("ERROR:OLED") == std::string::npos);
    return 0;
  }
  assert(!saidaPronta && !armado && !iniciar && testPwmCalls == 0);
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
    assert(!saidaPronta && !armado && comandoAtual == 's');
  }
  send("CONFIG:OL");
  assert(!saidaPronta);
  SerialComando.output.clear();
  send("ED:0\r\n");
  assert(usarOled && !usarUltrassonico && saidaPronta && iniciar && !armado);
  assert(SerialComando.output == "CONFIG_OK:OLED:0\nINICIAR:1\nARMING\n");
  assert(Wire.sda == OLED_SDA && Wire.scl == OLED_SCL && testPwmCalls == 0);
  testClock = inicio + 3000;
  loop();
  send("w\n");
  assert(display.shown.find("CMD: w") != std::string::npos);
  assert(testPwmCalls == 0);

  // Um pedido durante movimento para e e rejeitado; a proxima execucao envia s antes.
  send("CONFIG:MOTORES:1\n");
  assert(usarOled && comandoAtual == 's');
  assert(SerialComando.output.find("ERROR:CONFIG_EM_MOVIMENTO") != std::string::npos);
  send("CONFIG:MOTORES:1\n");
  assert(!usarOled && usarUltrassonico && saidaPronta && !armado && !iniciar);
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
  assert(display.shown.find("CMD: w") != std::string::npos);
  assert(display.shown.find("Dist: 12.0 cm") != std::string::npos);

  send("s\nCONFIG:OLED:1\n");
  assert(usarOled && usarUltrassonico && !iniciar && !armado);
  assert(testDetachCalls == 2);
  assert(testDigitalValues[12] == LOW && testDigitalValues[13] == LOW);
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
  assert(!usarOled && !usarUltrassonico && iniciar && !armado);
  testEchoDuration = 0;
  testClock = inicio + 3000;
  loop();
  send("d\n");
  assert(alvo1 == 1000 && alvo2 == 1300);
  assert(display.shown.find("CMD: d") != std::string::npos);
  testEchoDuration = 700;
  testClock += 100;
  loop();
  assert(iniciar && display.shown.find("Dist: 12.0 cm") != std::string::npos);
  testEchoDuration = 0;
  testClock += 100;
  loop();
  assert(iniciar && display.shown.find("Dist: sem eco") != std::string::npos);
  testClock = ultimoComando + 3000;
  loop();
  assert(atual1 == 1000 && atual2 == 1000 && comandoAtual == 's');
  assert(display.shown.find("CMD: s") != std::string::npos);

  // Se apenas um ESC inicializar, libere ambos antes de aceitar outro modo.
  for (int esc = 0; esc < 2; ++esc) {
#if TEST_CORE_VERSION >= 3
    const uint8_t failingOutput = esc == 0 ? ESC_PIN1 : ESC_PIN2;
#else
    const uint8_t failingOutput = esc;
#endif
    testPwmFailures[failingOutput] = true;
    SerialComando.output.clear();
    send("CONFIG:MOTORES:0\n");
    assert(SerialComando.output == "ERROR:PWM\n");
    assert(!saidaPronta && !armado && !iniciar && comandoAtual == 's');
    assert(!testPwmAttached[ESC_PIN1] && !testPwmAttached[ESC_PIN2]);
    assert(testPinModes[ESC_PIN1] == OUTPUT && testPinModes[ESC_PIN2] == OUTPUT);
    assert(testDigitalValues[ESC_PIN1] == LOW && testDigitalValues[ESC_PIN2] == LOW);
    send("w\n");
    assert(comandoAtual == 's');
    testPwmFailures[failingOutput] = false;
    const uint32_t failedPwmCalls = testPwmCalls;
    send("CONFIG:OLED:0\n");
    assert(usarOled && saidaPronta && iniciar && !armado);
    assert(!testPwmAttached[ESC_PIN1] && !testPwmAttached[ESC_PIN2]);
    assert(testPwmCalls == failedPwmCalls);
  }

  // Uma tentativa posterior valida continua podendo controlar e parar os ESCs.
  send("CONFIG:MOTORES:0\n");
  assert(saidaPronta && iniciar && !armado);
  assert(testPwmAttached[ESC_PIN1] && testPwmAttached[ESC_PIN2]);
  testClock = inicio + 3000;
  loop();
  send("w\n");
  assert(alvo1 == 1300 && alvo2 == 1300);
  send("s\n");
  assert(atual1 == 1000 && atual2 == 1000);
  std::cout << "OK: configuracao UART, quatro modos, parada e troca de saidas\n";
}
