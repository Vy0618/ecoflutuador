# EcoFlutuador V4 — Raspberry

O nome da pasta `poc_raspberry` foi preservado para não quebrar instalação e imports.
O código nesta pasta é o entrypoint V4 atual, separado dos servidores legados da raiz.

Consulte [operação atual](../docs/OPERACAO_V4.md), [auditoria](../docs/AUDITORIA_V4.md),
[resultados](../docs/RESULTADO_V4.md) e [pinagem](../PINAGEM_V4.md).
O README anterior foi preservado no arquivo `docs/audit/original-sources.tar.gz`;
continha pinos incorretos e uma afirmação de failsafe não implementada no baseline.

Da raiz:

```bash
python3 -m unittest discover -s poc_raspberry/tests -v
python3 poc_raspberry/main.py mock --simulate-start-after 2 --simulate-clear-after 10 --duration 12
```

Os modelos originais continuam incompatíveis. Mock é explícito; falha de detector
nunca é convertida silenciosamente em reconhecimento simulado. Não iniciar motores
em testes. Nenhum serviço é instalado automaticamente.
