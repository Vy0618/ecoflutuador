# Revisão da aproximação autônoma do EcoFlutuador V4.1

Data: 12/10/2026, 16:05:33, America/Sao_Paulo (UTC−03:00).

> Atualização de 15/10/2026: a parada na faixa inferior passou a usar o centro
> da caixa, em vez de `ymax`. Este relatório preserva os critérios da revisão original.

Objetivo: adequar o percurso entre detecção e parada ao fluxo solicitado,
preservando o SSD MobileNet, a câmera, a interface gráfica, os registros e o
protocolo de movimento do ESP32.

## Exame da implementação anterior às correções

| Etapa examinada | Local | Comportamento encontrado |
|---|---|---|
| Detecção | `detection/ssd_mobilenet_detector.py`, `SsdMobileNetDetector.detect` | SSD MobileNet via OpenCV DNN; filtro de confiança e classe `bottle`; caixas `x1,y1,x2,y2` |
| Coordenadas | `image_processing.py`, `restore_coordinates`; `detection/types.py`, `Detection.centroid` | Restauração para a resolução capturada e centro calculado pela média dos extremos |
| Região e decisão | `regions.py`; `navigation.py`, `Navigation.update` | Seleção da maior caixa em cada inferência; centro usado tanto na horizontal quanto na vertical; esquerda→`a`, meio→`w`, direita→`d`, baixo→`s` |
| Transmissão | `object-ident.py`, ciclo principal; `esp32_link.py`, `Esp32Link.send` | Porta habilitada por argumento; consulta `?`, espera `READY`, envio com nova linha e confirmação `CMD_OK`; repetição a cada inferência |
| Parada no Python | `Navigation.update`, `Navigation.stop`, encerramento de `object-ident.py` | `s` sem detecções, na faixa inferior e ao finalizar; confirmação da parada antes de fechar a porta |
| Parada e motores no ESP32 | `firmware/ControleESP32/ControleESP32.ino`, `parar`, `executarComando`, `loop` | Pulso mínimo imediato em ambos os ESCs; watchdog de três segundos; armamento e rampa sem bloquear a serial |
| Visualização | `object-ident.py`, `annotate` e ciclo da webcam | Vídeo habilitado por padrão, bounding boxes, centro do alvo, três regiões superiores e faixa inferior |

Já atendiam ao objetivo: inferência contínua conforme intervalo configurado,
captura do frame recente, restauração de coordenadas, comando central `w`, parada
`s`, confirmações seriais, watchdog, rampa e desenho compartilhando a geometria.
Esses componentes foram mantidos.

As inconsistências principais eram o mapeamento lateral oposto ao solicitado,
parada somente pelo centro vertical, possibilidade de retomar a aproximação após
atingir a faixa inferior, troca de alvo pela maior caixa a cada inferência,
ausência de histerese e repetição de movimentos pela serial. A inicialização
também podia interpretar um segundo `READY` de partida como reinicialização.

## Correções aplicadas

### Decisão e acompanhamento

O centro horizontal da bounding box determina o comando lógico. A serial usa os
mesmos bytes minúsculos aceitos pelo firmware:

| Região | Comando lógico / serial | Acionamento preservado |
|---|---|---|
| Esquerda | `D` / `d` | Somente motor direito, ESC 2, GPIO 14 |
| Centro | `W` / `w` | Ambos os motores |
| Direita | `A` / `a` | Somente motor esquerdo, ESC 1, GPIO 12 |
| Inferior, sem alvo válido ou aproximação encerrada | Parada / `s` | Ambos no pulso mínimo |

A aproximação termina quando `bbox[3]`, isto é, `ymax`, é maior ou igual à linha
horizontal existente. Com o perfil atual, isso corresponde a `y=384` em uma
imagem de 640×480. O centro da caixa pode ainda estar acima da linha.

O estado de aproximação encerrada mantém `s` enquanto a garrafa acompanhada
continua sendo associada, inclusive se sua caixa recuar acima da linha. Isso
indica proximidade para coleta passiva pela rede; não confirma coleta física.
Nenhum contador automático de objetos coletados foi implementado.

São elegíveis apenas garrafas com confiança e coordenadas finitas, caixa com
área positiva e extremos dentro do quadro. A seleção inicial usa maior área,
seguida de confiança e coordenadas para desempate independente da ordem da rede.
As inferências seguintes associam o alvo por sobreposição das caixas (IoU) ou
distância entre centros. Outra garrafa ficar maior não basta para trocar o alvo.

Uma inferência sem associação válida envia `s` imediatamente. A referência é
conservada durante perdas breves; após três inferências consecutivas ausentes,
é liberada. Uma nova seleção pode ocorrer na inferência seguinte. A liberação
também limpa o estado de aproximação encerrada. Assim, o reconhecimento continua
ativo durante e depois da aproximação, sem exigir intervenção manual por alvo.

A histerese mantém a direção anterior perto de cada divisória. Para mudar de
região, o centro precisa ultrapassar a linha mais uma margem de 3% da largura
por padrão. A margem permanece durante perdas breves, sem atrasar a parada.

### Comunicação e proteção de parada

`Esp32Link` suprime comandos de movimento iguais ao estado já confirmado. O
firmware anuncia `CAPS:HEARTBEAT` na consulta e aceita `h`, respondendo `HB_OK`.
Esse heartbeat renova o watchdog sem alterar o estado ou os alvos dos ESCs.
O Python o envia no máximo uma vez por segundo e apenas ao processar uma decisão
recente; não existe renovação independente que sustente movimento com inferência
ou câmera bloqueada.

O firmware anterior do V4.1, com `READY` e `CMD_OK` e sem essa capacidade,
permanece compatível. Nesse caso, o comando de movimento é renovado no máximo
uma vez por segundo para manter seu watchdog. Para eliminar essas renovações,
é necessário gravar o sketch atualizado. O firmware original do V3 não possui
as confirmações exigidas pelo protocolo atual do V4.1.

Ausência de confirmação, envio parcial, erro do firmware, timeout informado ou
reinicialização detectada provocam tentativa de envio de `s` e encerramento da
execução. A ligação fica impedida de autorizar novo movimento após a falha. Se
a serial estiver totalmente indisponível, a tentativa de parada não pode ser
garantida pelo computador: o ESP32 aplica o watchdog de três segundos.

A confirmação inicial tolera um `READY` duplicado antes da primeira parada
confirmada. Os comandos de movimento, GPIOs, potência, armamento, rampa e timeout
foram preservados no firmware. Apenas o anúncio de capacidade e o heartbeat
foram acrescentados.

### Visualização, configuração e registros

O vídeo permanece habilitado por padrão; `--no-display` é a opção para operação
headless. As linhas e caixas continuam visíveis. Os rótulos laterais mostram o
mapeamento corrigido, e a janela indica quando a aproximação está encerrada.

`config.json` recebeu parâmetros de histerese e associação do alvo na seção
`navigation`. Perfis antigos sem essa seção recebem os mesmos valores padrão.
Os ajustes existentes de FPS, intervalo, modelo e confiança foram preservados.

O formato de quatro campos do terminal foi mantido. O JSONL acrescenta `ymax`,
estado da navegação e indicação de aproximação encerrada. `garrafas_detectadas`
continua representando detecções no quadro, sem indicar coleta realizada.

## Arquivos alterados nesta revisão

| Arquivo | Alteração |
|---|---|
| `regions.py` | Validação, seleção determinística, associação geométrica e suporte a `ymax` |
| `navigation.py` | Mapeamento lateral, acompanhamento, histerese, parada persistente e campos de log |
| `config.py` e `config.json` | Parâmetros de navegação, padrões e validação |
| `object-ident.py` | Uso da configuração de navegação e atualização dos rótulos e estado na imagem |
| `esp32_link.py` | Supressão, heartbeat negociado, compatibilidade anterior e tratamento de falhas |
| `firmware/ControleESP32/ControleESP32.ino` | Anúncio de capacidade e renovação sem repetir acionamento |
| `tests/test_navigation.py`, `tests/test_esp32_link.py`, `tests/test_video_display.py`, `tests/firmware_behavior.cpp` | Casos de regressão e integração |
| `tests/test_config_navigation.py` | Novo teste de padrões e parâmetros inválidos |
| `README.md` da raiz e do V4.1 | Fluxo, comandos, protocolo, configuração e evidências atualizados |
| `docs/REVISAO_AUTONOMIA.md` | Análise e registro desta revisão |

## Validação realizada

- **37 testes aprovados**, sem câmera ou serial físicas. Cobrem acompanhamento,
  múltiplos alvos, histerese, `ymax`, persistência da parada, perda do alvo,
  caixas inválidas, serial com falhas, heartbeat, compatibilidade e vídeo padrão.
- O ciclo principal foi exercitado com `Navigation` e `Esp32Link` reais e uma
  serial simulada: alvo à esquerda → centro → direita → inferior → pequeno recuo,
  resultando em `d → w → a → s → s`.
- O firmware foi simulado nos caminhos Arduino-ESP32 2.x e 3.x, incluindo
  acionamentos, rampa, heartbeat, parada, watchdog e rollover de `millis()`.
- Compilação PlatformIO para `esp32dev`, Espressif32 7.0.1 e core 2.0.17:
  **sucesso**, 21.592 bytes de RAM e 274.713 bytes de programa.
- O SSD real carregou e executou inferência sobre uma imagem sintética vazia.
  A saída anotada manteve a dimensão de 640×480 e as três linhas divisórias.
  Esse ensaio verifica execução e desenho, sem medir precisão do reconhecimento.
- `pip check`: nenhuma dependência incompatível. `git diff --check`: sem erros.

O firmware não foi gravado em uma placa nesta revisão, nem houve acionamento
físico dos motores. A janela foi verificada por testes com funções gráficas
simuladas; não houve validação visual ao vivo com webcam. A montagem deve associar
ESC 1 ao motor esquerdo e ESC 2 ao direito para corresponder à tabela solicitada.

O acompanhamento usa geometria, sem identificação visual individual. Garrafas
sobrepostas ou cruzando trajetórias podem tornar a associação ambígua. O tempo
de reação depende do intervalo de inferência e do processamento; falhas completas
de comunicação dependem do watchdog. Não há confirmação física de coleta nem
métrica de precisão do detector nesta validação.

## Execução autônoma

Após gravar o firmware do V4.1 e identificar a porta do ESP32:

```bash
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0
```

Acrescente `--no-display` para operar sem janela. Sem `--serial-port`, a mesma
decisão é executada e registrada, sem enviar comandos aos motores.

## Localização atual do projeto

O V4.1 foi promovido à raiz do repositório. Os comandos acima usam os caminhos
atuais; as descrições das etapas anteriores mantêm o nome da versão. Veja o
[registro da migração](MIGRACAO_PARA_RAIZ.md).
