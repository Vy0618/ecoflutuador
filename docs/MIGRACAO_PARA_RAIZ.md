# Migração do V4.1 para a raiz

Data: 12/10/2026, 16:12:49, America/Sao_Paulo (UTC−03:00).

O EcoFlutuador V4.1 passou a ser o projeto principal na raiz do repositório.
A pasta `V4.1/` foi removida após a movimentação de todo o seu conteúdo.

## Organização atual

- Entrada: `object-ident.py`.
- Configuração: `config.json` e `config.py`.
- Módulos: `camera.py`, `image_processing.py`, `navigation.py`, `regions.py`,
  `esp32_link.py`, `command_log.py` e `detection/`.
- Modelo SSD MobileNet e arquivos auxiliares: `models/`.
- Firmware: `firmware/ControleESP32/`.
- Testes e documentos: `tests/` e `docs/`.
- Dependências e ambiente principal: `requirements.txt`, `requirements-lock.txt`
  e `.venv/`.
- Registros existentes e futuros: `logs/`.

O README completo do V4.1 substituiu o README da raiz. O README, as dependências
e o arquivo de versões anteriormente presentes na raiz foram preservados em
`docs/historico-raiz/`. O ambiente anterior foi preservado em `.venv-anterior/`.
O AquaMonitor permanece em seu diretório de referência.

Os scripts e a configuração do ambiente principal foram ajustados para o novo
local, preservando as bibliotecas instaladas e o OpenCV com suporte gráfico.
Os scripts do ambiente anterior também foram ajustados para seu local de arquivo.
As regras dos dois `.gitignore` foram reunidas na raiz, incluindo logs, saídas
do PlatformIO e o ambiente anterior.

`requirements.txt` define as três dependências do projeto principal:
OpenCV, NumPy e pyserial. `requirements-lock.txt` registra as versões exatas
instaladas nesse ambiente, substituindo o conjunto de dependências anterior.

Os módulos resolvem configuração, modelos e logs a partir da localização dos
arquivos; esses caminhos acompanharam a mudança. Os comandos dos documentos
ativos foram atualizados. A lógica de detecção, acompanhamento e motores foi
preservada.

## Comandos atuais

Execute a partir da raiz do repositório:

```bash
# Vídeo habilitado por padrão
.venv/bin/python object-ident.py

# Sem janela
.venv/bin/python object-ident.py --no-display

# Operação autônoma com ESP32, usando a porta correspondente à placa
.venv/bin/python object-ident.py --serial-port /dev/ttyUSB0

# Testes
.venv/bin/python -B -m unittest discover -s tests -v

# Compilação do firmware
pio run --project-dir firmware/ControleESP32 --environment esp32
```

Para ativar o ambiente no terminal: `source .venv/bin/activate`.

## Verificações

- 37 testes aprovados nos novos caminhos.
- SSD real carregado e executado sobre imagem sintética vazia, inclusive com o
  programa iniciado a partir de outro diretório. Configuração, imagem anotada,
  divisórias e JSONL funcionaram.
- Ambiente ativado com Python, pip, OpenCV com GUI Qt5 e pyserial corretos.
- `pip check`: nenhuma dependência incompatível.
- Firmware compilado com sucesso no novo diretório para `esp32dev`:
  21.592 bytes de RAM e 274.713 bytes de programa.
- Ambientes, logs e saídas de compilação confirmados como ignorados pelo Git.

Nenhuma placa foi gravada nem houve acionamento físico dos motores nesta
migração. As evidências anteriores permanecem nos relatórios da sessão e da
revisão da autonomia.
