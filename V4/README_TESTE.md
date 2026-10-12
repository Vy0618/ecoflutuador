# Reconhecimento com interface grafica — V4

Da raiz do repositorio:

```bash
source V4/.venv/bin/activate
python V4/poc_raspberry/preview.py
```

Abre a webcam 0 em uma janela OpenCV e inicia reconhecimento continuo no modo
automatico. Execute em um terminal da sessao grafica do computador.
Para outra webcam: `python V4/poc_raspberry/preview.py --camera-index 1`.

Sem webcam, para entender a movimentacao entre as zonas:

```bash
python V4/poc_raspberry/preview.py --mock
```

O mock acompanha um retangulo verde sintetico; nao reconhece objetos reais.

## Como interpretar

- Linhas amarelas dividem a imagem em esquerda (`a`), frente (`w`) e direita (`d`).
- Caixas verdes sao garrafas (`bottle`), o alvo deste perfil.
- A caixa mais grossa, o ponto central e a linha indicam o alvo selecionado.
- Somente garrafas (`bottle`) sao retornadas pelo detector e desenhadas na tela.
- O painel mostra confianca nas caixas, direcao sugerida, motivo e tempo de inferencia.
- A zona atual fica destacada no titulo. Sem alvo, o comando e `s` (parado).

Mostre uma garrafa a webcam e mova-a de um lado ao outro. A decisao usa o
maior alvo, como no automatico do V3, e preserva as regras do DecisionEngine V4:
tres frames para confirmar mudanca, histerese de 4% nas fronteiras e tolerancia
de 0,5 s a perda do alvo. Esses intervalos podem fazer a direcao mostrada diferir
temporariamente da posicao geometrica do objeto.

Espaco alterna automatico/pausa; `R` limpa as confirmacoes e reinicia a decisao;
`Q`, `Esc`, fechar a janela ou `Ctrl+C` encerram.

Este preview calcula direcoes para observacao. Nao abre serial, nao envia
comandos, nao inicia API. Reconhecimento e continuo, sem o gatilho HC-SR04 nem
a janela de 15 segundos de `main.py`. O fluxo de controle existente continua
usando sua configuracao original.

## Modelo real usado pelo preview

`config.preview.yaml` usa um novo par SSD MobileNet V1 COCO 2017-11-17,
separado dos pesos e da configuracao V3 incompatíveis existentes.

- [Pesos no mirror oficial OpenCV](https://mirror.opencv.ai/ssd_mobilenet_v1_coco_2017_11_17.pb)
- [Grafo no repositorio oficial OpenCV](https://github.com/opencv/opencv_extra/blob/4.x/testdata/dnn/ssd_mobilenet_v1_coco_2017_11_17.pbtxt)
- [Classes oficiais TensorFlow COCO](https://github.com/tensorflow/models/blob/master/research/object_detection/data/mscoco_label_map.pbtxt)

`models/coco_ssd.names` mantem os IDs COCO 1–90, inclusive lacunas, para nao
confundir os nomes das classes. A rede SSD continua sendo um modelo COCO de
varias classes, mas o preview filtra seus resultados para retornar apenas
garrafas. Outros objetos nao aparecem nas caixas nem influenciam a decisao.
Iluminacao, tamanho do objeto e enquadramento influenciam o reconhecimento.

O grafo V1 normaliza pixels internamente: o perfil usa entrada 300x300,
escala 1 e media zero. Usar a normalizacao legada novamente derruba a confianca.

## Instalar em outro ambiente

No `V4/.venv` deste computador, OpenCV com GUI ja foi instalado. Para recriar:

```bash
python3 -m venv V4/.venv
V4/.venv/bin/python -m pip uninstall -y opencv-python-headless opencv-contrib-python-headless
V4/.venv/bin/python -m pip install -r V4/poc_raspberry/requirements-gui.txt
```

Use somente uma distribuicao OpenCV no ambiente, pois todas fornecem `cv2`.
`requirements-dev.txt` instala a variante headless para testes sem janela;
`requirements-gui.txt` instala a variante grafica.

Para reconhecer uma imagem e salvar as anotacoes sem camera/janela:

```bash
python V4/poc_raspberry/preview.py --image foto.jpg --output resultado.jpg
```

Uma imagem isolada conta como apenas uma confirmacao, portanto pode mostrar
`Confirmando direcao ... 1/3` e permanecer em `s`, mesmo com alvo reconhecido.
