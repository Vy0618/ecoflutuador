# V4.1 — SSD MobileNet V3 do AquaMonitor

Detector, pesos TensorFlow, grafo `.pbtxt`, classes COCO, captura de webcam e
preparacao de frames copiados de `aquamonitor`. Os imports foram ajustados para
os modulos locais. `models/origem.json` registra os arquivos de origem e hashes.

`config.json` configura somente os recursos atuais do V4.1, usando o AquaMonitor
como referencia:
camera 640×480/15 FPS, entrada SSD 320×320, limiar 0,45, alvo `bottle`, intervalo
de deteccao 250 ms e limites de processamento. A janela foi habilitada neste
perfil. Os tres caminhos de modelos foram alterados para `models/` e sao
resolvidos relativamente ao JSON, independentemente do diretorio do terminal.

| Secao | O que controla |
|---|---|
| `headless` | `true` executa sem janela; `false` permite a janela conforme `display.enabled` |
| `camera` | Webcam, resolucao de captura e limite de FPS da aplicacao |
| `ssd_mobilenet` | Arquivos locais do modelo, limiar de confianca, tamanho da entrada e alvo `bottle` |
| `detection_interval_ms` | Intervalo minimo entre inferencias, em milissegundos |
| `image_processing` | Reducao opcional do frame antes da inferencia, com restauracao das coordenadas |
| `display` | Janela grafica e posicao da linha que separa a faixa baixo |

O perfil usa apenas SSD MobileNet. As secoes `detection` (YOLO) e `tracking`
(contagem de cruzamentos, direcao e associacao de objetos) nao fazem parte deste
fluxo. `nms_threshold` foi removido porque o detector atual nao le esse parametro.

`camera.fps` e solicitado ao dispositivo e tambem limita por software a entrega
de frames ao processamento/exibicao. A captura em segundo plano continua drenando
a webcam para usar sempre a imagem mais recente, mesmo quando o driver mantem
outra taxa de captura. Inferencia e hardware lentos podem produzir menos FPS
que o limite solicitado. O terminal informa o FPS configurado, o reportado pela
webcam e o caminho da configuracao carregada.

`detection_interval_ms` controla separadamente o intervalo entre reconhecimentos
e seus registros: 250 ms permite no maximo aproximadamente quatro inferencias
por segundo, mesmo com video a 15 FPS. Para reconhecer a cada frame a 15 FPS,
use um intervalo menor que 66 ms, se o computador conseguir acompanhar.
As configuracoes sao lidas na inicializacao: reinicie o script apos editar o JSON.

Para abrir na raiz do repositorio com o ambiente proprio do V4.1:

```bash
V4.1/.venv/bin/python V4.1/object-ident.py
```

Mostre uma garrafa a webcam. As caixas exibem classe e confianca.
A imagem mostra quatro regioes: **esquerda**, **meio** e **direita** acima da
linha horizontal amarela, e **baixo** em toda a faixa inferior. As linhas
verticais terminam na horizontal, deixando a faixa inferior sem subdivisoes.
A linha horizontal fica a 80% da altura; ajuste `display.bottom_zone_ratio`
em `config.json` para mudar sua posicao. As divisoes e o comando atual tambem
aparecem nas imagens salvas com `--output`.

O sistema acompanha a garrafa com a maior caixa, como no V3/V4, e usa o centro
da caixa para determinar a regiao: **esquerda=a**, **baixo=s**, **meio=w**,
**direita=d**. A regiao baixo tem prioridade quando o centro esta abaixo da
horizontal. Sem garrafa detectada, o comando e **s**. Uma caixa que cruza uma
linha e classificada pela posicao do seu centro, sem exigir que toda a caixa
fique contida na regiao.

A cada inferencia, o terminal mostra um registro JSON com horario, numero,
regiao, comando, objeto, confianca, caixa e centro. `mudou_comando` informa se
o comando mudou desde a leitura anterior. A decisao atual e exibida na janela,
mesmo entre inferencias. O alvo escolhido tem caixa mais grossa e ponto central.
Ao encerrar, e registrado **s**. Nesta etapa os comandos sao somente registrados;
nao ha envio ao ESP32.

Os mesmos registros sao salvos em `V4.1/logs/recognition.jsonl`, com rotacao de
2 MB e ate tres arquivos anteriores. Use `--log-file caminho/arquivo.jsonl`
para alterar o destino. A pasta `logs/` e ignorada pelo Git.
`Q`, `Esc` ou fechar a janela encerram. Para outra camera: `--camera-index 1`.
Use `--config caminho/config.json` para outro perfil, ou `--no-display` para
executar sem janela. `--duration 5` limita a execucao a cinco segundos.

Para executar headless, defina `"headless": true` na raiz do `config.json` ou use:

```bash
V4.1/.venv/bin/python V4.1/object-ident.py --headless
```

O reconhecimento e os registros no terminal/arquivo continuam ativos sem abrir
janelas ou chamar funcoes de interface grafica do OpenCV. Encerre com `Ctrl+C`
ou limite o tempo com `--duration`. `--headless` (alias `--no-display`) e
`--no-headless` (alias `--display`) sobrescrevem o JSON nesta execucao.
O registro inicial da camera informa se o modo headless esta ativo.

Para reconhecer uma imagem sem abrir webcam/janela:

```bash
V4.1/.venv/bin/python V4.1/object-ident.py --image foto.jpg --output resultado.jpg
```

O ambiente `V4.1/.venv` ja esta criado neste computador. Para recria-lo:

```bash
python3 -m venv V4.1/.venv
V4.1/.venv/bin/python -m pip install -r V4.1/requirements.txt
V4.1/.venv/bin/python V4.1/object-ident.py
```

Esta pasta executa reconhecimento local de garrafas. Nao requer servidor
AquaMonitor, nao envia eventos HTTP e nao abre UART ou controla motores.
O detector usa o mesmo pre-processamento e decodificacao de caixas `xyxy`
do AquaMonitor.
