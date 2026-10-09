# EcoFlutuador V4

Entrypoint V4: **`poc_raspberry/main.py`**. Os arquivos `servidor*.py`, `Servidor 1.0/`, `object-ident.py`, `ControleESP32V2` e `ecoflutuador.service` são legados e não devem ser iniciados para V4.

- [Auditoria integral e baseline](docs/AUDITORIA_V4.md)
- [Operação, arquitetura, UART, detector, telemetria e comandos](docs/OPERACAO_V4.md)
- [Resultados finais, riscos e melhorias priorizadas](docs/RESULTADO_V4.md)
- [Pinagem vigente](PINAGEM_V4.md)

```bash
python3 -m unittest discover -s poc_raspberry/tests -v
python3 poc_raspberry/main.py mock --simulate-start-after 2 --simulate-clear-after 10 --duration 12
```

Dashboard de dados: http://localhost:8080 enquanto o mock estiver rodando. Sem hardware, UART física, motores ou vídeo. USB é o backend padrão; CSI é opcional. O MobileNet legado permanece incompatível e não foi substituído. Antes de qualquer operação física, consultar os riscos e pendências no relatório final.
