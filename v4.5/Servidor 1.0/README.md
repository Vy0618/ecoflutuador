# Servidor modular do EcoFlutuador V4.5

O servidor foi dividido seguindo o princípio de uma responsabilidade por módulo.
As peças se comunicam por objetos e funções explícitas. A divisão usa um único
processo Python; não exige subprocessos, microserviços ou troca de arquivos.

## Responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `servidor.py` | Compor a aplicação, iniciar componentes e encerrar recursos. |
| `config.py` | Configuração e ajustes por variáveis de ambiente. |
| `web.py` | Rotas Flask, template e arquivos públicos da interface. |
| `controller.py` | Coordenar modos, potência e autorização dos comandos. |
| `serial_manager.py` | Conexão, reconexão, framing, envio e leitura das confirmações da ESP32. |
| `camera.py` | Capturar imagens, receber processamento opcional e produzir MJPEG. |
| `detector.py` | Carregar SSD MobileNet, detectar e anotar garrafas. |
| `navigator.py` | Escolher `a`, `w`, `d` ou `s` pela posição das caixas. |
| `command_log.py` | Histórico de até 20 mensagens com acesso sincronizado. |
| `index.html`, `style.css`, `script.js` | Apresentação e interação no navegador. |

Fluxo automático: captura → controlador → detector → navegador → serial.
A imagem anotada da mesma inferência volta à câmera para codificação JPEG.
Fluxo manual: navegador → rotas HTTP → controlador → serial.

Importar os módulos não abre dispositivos, não carrega pesos e não inicia threads.
`Controller.start()` inicia serial e câmera; `Controller.stop()` solicita STOP
e libera os recursos. `create_app(controller)` permite verificar HTTP com
componentes substituídos, sem hardware.

## Execução

Na raiz do repositório, crie/ative o venv e instale `requirements.txt`, conforme
o [README principal](../../README.md). Depois execute:

```bash
python "v4.5/Servidor 1.0/servidor.py"
```

A interface fica na porta 8080. Serial e câmera reais são necessárias para esse
comando; uma falha na inicialização é explícita e libera os componentes iniciados.
O detector é carregado somente ao solicitar modo automático. Modelo ausente ou
incompatível impede essa troca, mantendo o modo manual disponível.

Configurações opcionais no Linux:

```bash
export ECO_SERIAL_PORT=/dev/ttyUSB0
export ECO_CAMERA_INDEX=0
export ECO_MODEL_DIR=/caminho/para/Object_Detection_Files
export ECO_HOST=0.0.0.0
export ECO_PORT=8080
python "v4.5/Servidor 1.0/servidor.py"
```

`ECO_MODEL_DIR` deve conter `coco.names`, `frozen_inference_graph.pb` e
`ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt`, com pesos/configuração compatíveis.
Os caminhos padrão e parâmetros básicos da V3 permanecem em `config.py`.
O backend de câmera continua V4L2, específico de Linux.

## Comportamento preservado e ajustes da divisão

- Rotas `/`, `/stream`, `/move`, `/power`, `/set_modo` e `/log` preservadas.
- Movimento manual `w/a/s/d/q/e` e potência `P1xxx`/`P2xxx`, sempre com newline.
- Detecção de `bottle`, confiança 0,45, NMS 0,2 e escolha da maior caixa.
- Zonas calculadas usando a largura real do frame.
- Vídeo MJPEG, sliders, histórico e troca de modos usam os arquivos de interface existentes.
- Uma inferência por captura substitui as duas inferências concorrentes do original.
- Ausência de alvo envia STOP inclusive no primeiro frame automático.
- Entrada e saída do automático solicitam STOP. Resultado de uma inferência anterior
  à troca de modo não pode enviar movimento após essa troca.
- Falha de inferência desativa o automático e tenta parar; a interface consulta o
  modo atual junto do log. Falha ao carregar o modelo retorna HTTP 500 com mensagem.
- Conexão/reconexão serial solicita STOP; perda da conexão desativa o automático.
- Arquivos públicos são limitados a CSS/JS, sem expor código Python por `/static`.

## Verificação sem hardware

Na raiz, com as dependências instaladas:

```bash
python -m unittest discover -s "v4.5/Servidor 1.0/tests" -v
```

Os testes substituem câmera, ESP32 e modelo. Verificam rotas, protocolo, decisões,
falhas, mudança de modo durante inferência e encerramento. Não validam comportamento
elétrico ou desempenho na Raspberry.

## Limites desta etapa

O firmware não foi alterado. A proteção por heartbeat/timeout ainda não existe
na V4.5: STOP por software depende de a serial e a ESP32 responderem. Queda física
do cabo ou travamento não garante parada no firmware legado.
Timeout/reconexão da câmera e supervisão de ACKs também ficam para uma próxima
etapa; desconexão da câmera pode deixar o último JPEG/comando disponível.
O modelo não foi substituído, e a compatibilidade dos seus arquivos precisa ser
verificada antes do uso automático. Pinagem e identificação física dos motores
continuam dependendo da conferência da montagem.
