# Ecoflutuador V4 — pinagem vigente

| Componente / sinal | GPIO ESP32 | Observação |
|---|---:|---|
| Motor / ESC 1 | 12 | Preservado; PWM desabilitado na compilação de teste |
| Motor / ESC 2 | 14 | Preservado; PWM desabilitado na compilação de teste |
| Raspberry TX → ESP32 RX | 16 | UART2, 115200 baud |
| ESP32 TX → Raspberry RX | 17 | UART2, 115200 baud |
| GPS TX → ESP32 RX | 27 | UART1, 9600 baud |
| ESP32 TX → GPS RX | 26 | UART1, 9600 baud |
| PH4502C analógico | 34 | ADC; calibração e habilitação existentes preservadas |
| ST100 analógico | 35 | ADC; calibração e habilitação existentes preservadas |
| HC-SR04 TRIG | 33 | Saída digital |
| HC-SR04 ECHO | 32 | **Divisor resistivo externo para 3,3 V**, conforme montagem prevista |
| HW-870 DO, entrada da rede | 25 | Entrada com pull-up; nível ativo LOW configurável |

O GPIO 32 deixa de ser a entrada digital opcional do ST100. O campo legado
`water.turbidity_digital` permanece no JSON, com `null`. O HW-870 deixa de ser
START: essa função passa exclusivamente ao HC-SR04. Compartilhar GND entre os
dispositivos de sinal; preservar o condicionamento elétrico dos sensores analógicos.
O software não substitui o divisor do ECHO.

As constantes ficam no início de `ControleESP32.ino`. GPS, pH e turbidez continuam
com suas habilitações e calibrações anteriores. HC-SR04 e rede começam habilitados.
Nenhum teste deve alimentar/acionar motores; a compilação padrão não faz attach
nos ESCs. O mapeamento operacional dos motores foi preservado.
