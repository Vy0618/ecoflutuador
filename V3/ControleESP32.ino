#include <Arduino.h>
#include <ESP32Servo.h>

#define ESC_PIN1 12
#define ESC_PIN2 14

Servo esc1;
Servo esc2;

int potencia1 = 30;
int potencia2 = 30;
int micro1Atual = 1000;
int micro2Atual = 1000;

#define PASSO 15
#define INTERVALO_MS 20

int pctParaMicro(int pct) {
  pct = constrain(pct, 0, 100);
  return map(pct, 0, 100, 1000, 2000);
}

void rampa(int alvo1, int alvo2) {
  while (micro1Atual != alvo1 || micro2Atual != alvo2) {
    if (micro1Atual < alvo1) micro1Atual = min(micro1Atual + PASSO, alvo1);
    else if (micro1Atual > alvo1) micro1Atual = max(micro1Atual - PASSO, alvo1);

    if (micro2Atual < alvo2) micro2Atual = min(micro2Atual + PASSO, alvo2);
    else if (micro2Atual > alvo2) micro2Atual = max(micro2Atual - PASSO, alvo2);

    esc1.writeMicroseconds(micro1Atual);
    esc2.writeMicroseconds(micro2Atual);
    delay(INTERVALO_MS);
  }
}

void parar() {
    rampa(1000, 1000);
}

void avancar() {
    rampa(
        pctParaMicro(potencia2), // esquerdo
        pctParaMicro(potencia1)  // direito
    );
}

void esquerda() {
    rampa(
        pctParaMicro(potencia2), // esquerdo ON
        1000                     // direito OFF
    );
}

void direita() {
    rampa(
        1000,                    // esquerdo OFF
        pctParaMicro(potencia1)  // direito ON
    );
}

void girarEsq() {
    rampa(
        1000,
        pctParaMicro(potencia1)
    );
}

void girarDir() {
    rampa(
        pctParaMicro(potencia2),
        1000
    );
}

void lerPotencia(String linha) {
  // Formato "P1045" → motor 1, 45%
  // Formato "P2070" → motor 2, 70%
  if (linha.startsWith("P") && linha.length() == 5) {
    int motor = linha.substring(1, 2).toInt();
    int val   = linha.substring(2).toInt();
    val = constrain(val, 0, 100);
    if (motor == 1) {
      potencia1 = val;
      Serial.print("PWR_OK:1:");
      Serial.println(potencia1);
    } else if (motor == 2) {
      potencia2 = val;
      Serial.print("PWR_OK:2:");
      Serial.println(potencia2);
    }
  }
}

void executarComando(char cmd) {
  switch (cmd) {
    case 'w': avancar();   break;
    case 'a': esquerda();  break;
    case 'd': direita();   break;
    case 'q': girarEsq();  break;
    case 'e': girarDir();  break;
    case 's': parar();     break;
  }
  Serial.print("CMD_OK:");
  Serial.println(cmd);
}

void setup() {
  Serial.begin(115200);
  esc1.attach(ESC_PIN1, 1000, 2000);
  esc2.attach(ESC_PIN2, 1000, 2000);
  Serial.println("Armando ESC...");
  parar();
  delay(3000);
  Serial.println("Pronto!");
}

void loop() {
  if (Serial.available() > 0) {
    String entrada = Serial.readStringUntil('\n');
    entrada.trim();

    if (entrada.startsWith("P")) {
      lerPotencia(entrada);
    } else if (entrada.length() == 1) {
      executarComando(entrada[0]);
    }
  }
}
