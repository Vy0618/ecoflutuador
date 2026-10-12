# Revisão dos arquivos V4 — 09/10/2026

A limpeza inicial pode remover os servidores antigos, o experimento de detecção
antigo, a unidade systemd antiga, o README vazio, o placeholder de modelos e os
artefatos de compilação. A aplicação atual não depende desses arquivos.
Nenhum arquivo do projeto foi apagado ou movido nesta revisão.

O conjunto antigo de modelos é candidato à remoção posterior: o preview já usa
o conjunto novo, mas o pipeline principal e um teste ainda dependem dos caminhos
antigos. Excluí-lo agora deixa referências pendentes e quebra um teste.

## Escopo e evidências

Inventário de 89 arquivos presentes antes deste relatório, incluindo arquivos
ignorados pelo Git, fontes, configurações, documentação, evidências da auditoria,
modelos e seis artefatos de compilação. O venv e os caches foram inventariados
separadamente; bibliotecas instaladas não são fontes do projeto.

Foram revisados os fontes e documentos, imports Python, caminhos de modelos,
templates, ferramentas de build/teste, os grafos textuais dos modelos, os
manifestos históricos e o conteúdo do arquivo de fontes históricas. Binários
foram examinados por tamanho, hash e função; não representam código textual.
O perfil de rede foi examinado sem registrar seus valores privados neste relatório.

[Inventário por arquivo, com classificação, tamanho e SHA256](audit/inventario-organizacao-v4.json).
Esse inventário é uma fotografia anterior à criação dos dois arquivos desta revisão.

## Arquivos que podem ser apagados na limpeza inicial

Todos os caminhos abaixo são relativos a `V4/`.

| Arquivo ou pasta | Motivo | Evidência e efeito da remoção |
|---|---|---|
| `Servidor 1.0/servidor.py` | Servidor Flask monolítico anterior; abre serial/câmera, serve MJPEG e controle remoto | Não é importado pelo código atual. Substituído pelo pipeline `main.py`, pela API de dados e pelo preview local |
| `Servidor 1.0/index.html` | Interface do servidor anterior | Só é servido pelo servidor legado |
| `Servidor 1.0/script.js` | Comandos `/move`, `/power`, `/set_modo` e `/log` do servidor anterior | Não usado pelo dashboard atual, que tem seu próprio template |
| `Servidor 1.0/style.css` | Estilos da interface anterior | Só referenciado pelo HTML legado |
| `Servidor 1.0/readme` | Nota de início da modularização | Histórico, sem instruções vigentes |
| `object-ident.py` | Experimento anterior com caminhos absolutos e uso de `cv2` sem import | Não é o detector V4. O reconhecimento com janela está em `poc_raspberry/preview.py` |
| `ecoflutuador.service` | Serviço anterior apontando para `/home/eco/servidor.py` | A referência atual é `configs/ecoflutuador-v4.service`. Apagar o arquivo do repositório não desinstala uma unidade já instalada no sistema |
| `readme` | Arquivo vazio, zero bytes | A documentação vigente é `README.md` |
| `poc_raspberry/models/.gitkeep` | Placeholder com instruções para o conjunto antigo de modelos | A pasta já contém modelos reais versionáveis; o placeholder não é lido pelo código |
| `build/firmware/ControleESP32.ino.bin` | Binário gerado antigo | Regenerado pelo helper de compilação |
| `build/firmware/ControleESP32.ino.bootloader.bin` | Bootloader gerado antigo | Regenerado pelo helper de compilação |
| `build/firmware/ControleESP32.ino.partitions.bin` | Tabela de partições gerada antiga | Regenerada pelo helper de compilação |
| `build/firmware/ControleESP32.ino.merged.bin` | Imagem de flash gerada antiga | Regenerada pelo helper de compilação |
| `build/firmware/ControleESP32.ino.elf` | Executável/símbolos da compilação antiga | Não usado pelo Python nem pelos testes nativos atuais |
| `build/firmware/ControleESP32.ino.map` | Mapa de memória da compilação antiga | Não usado pela aplicação |
| `**/__pycache__/`, fora do venv | Bytecode gerado do Python | Recriado automaticamente; não remover as fontes correspondentes |

Os oito arquivos de legado/vazio acima, antes do placeholder e do build, são
idênticos byte a byte aos exemplares de
[`original-sources.tar.gz`](audit/original-sources.tar.gz). O histórico deles já
está preservado. Esse arquivo compactado não contém modelos nem binários de build.

Os seis artefatos de build têm exatamente os hashes do manifesto anterior à
consolidação. Portanto são os mesmos artefatos históricos, e não prova de uma
compilação do firmware atual. O diretório ocupa 24.993.203 bytes, cerca de
23,84 MiB. Os caches externos ao venv ocupavam cerca de 0,41 MiB.

O helper `tools/compile_firmware.py` cria novamente `build/firmware/` quando
executado com a toolchain Arduino disponível. Nenhuma compilação ou upload foi
executado nesta revisão.

## Remover somente depois de migrar as referências

| Arquivo | Situação | Ajuste necessário antes da exclusão |
|---|---|---|
| `poc_raspberry/models/frozen_inference_graph.pb` | Pesos antigos; diferentes do novo `.pb`, não são duplicação byte a byte | Migrar `config.yaml`, defaults de `main.py` e o teste de existência de pesos |
| `poc_raspberry/models/ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt` | Configuração V3 incompatível com os pesos antigos V1 | Migrar configuração/defaults e mensagens do detector |
| `poc_raspberry/models/coco.names` | Lista antiga de 80 nomes; não corresponde aos IDs com lacunas do SSD novo | Migrar para `coco_ssd.names`, preservando posições 1–90 |

Referências concretas: seção `model` de `poc_raspberry/config.yaml`, construção de
`ModelConfig` em `Pipeline._setup()` de `main.py`, mensagens de arquivos ausentes
em `core/detector.py` e `ConfigTests.test_paths_relative_to_yaml` em
`tests/test_consolidation.py`.

A migração não consiste em copiar só os três caminhos de `config.preview.yaml`.
O modelo novo usa entrada 300×300, escala 1 e média zero. O pipeline principal
atualmente não repassa `input_scale`/`input_mean` do YAML para `ModelConfig`, embora
o preview já repasse. Isso precisa ser ajustado e validado junto com os caminhos.

Essa segunda limpeza liberaria aproximadamente 28,01 MiB. Não foi incluída na
simulação da limpeza inicial.

## Histórico e configuração particular

| Arquivo ou grupo | Recomendação | Motivo |
|---|---|---|
| `TESTE_V4_HCSR04.md` | Mover futuramente para uma área de documentos históricos, ou consolidar o roteiro útil | Já se declara histórico, registra 58 testes e termina com compilação “em verificação”. Também conserva um roteiro de bancada útil. A cópia atual difere da arquivada: preservar o conteúdo atual antes de descartá-lo |
| `docs/audit/phase-core-tests.txt`, `phase-api-tests.txt`, `phase-regression-tests.txt`, `phase-final-tests.txt` | Arquivar; exclusão é opcional se o histórico das etapas for dispensável | Evidências intermediárias de 58/82 testes; não são usadas em execução. Não há necessidade de eliminá-las para organizar o código |
| Demais `docs/audit/*.txt` e `*.json` | Manter como evidência histórica | Sustentam os relatórios de auditoria, resultados, desempenho e protocolo. Vários têm links na documentação |
| `docs/audit/original-sources.tar.gz` | Manter | Cópia de recuperação dos fontes anteriores; especialmente útil se o legado for removido |
| `ESP32-EcoFlutuador.nmconnection` | Guardar como configuração privada fora da árvore de fontes, caso ainda seja usado | Perfil NetworkManager, sem referência no código V4 e ignorado pelo Git raiz. Contém uma linha de sintaxe inválida. Uso em um equipamento instalado não pode ser determinado apenas pelo repositório |
| `.venv/` | Manter neste computador | Ambiente que acabamos de instalar e que permite usar o preview. É recriável e não deve ser versionado; não é um arquivo obsoleto |

Os relatórios de auditoria descrevem o estado de setembro. Declarações como
“nenhum modelo novo”, “câmera indisponível” e “Git indisponível” são fatos daquela
execução, não o estado atual do workspace. Devem continuar identificadas como
histórico, em vez de serem tratadas como instruções atuais.

## Arquivos em uso que devem permanecer

| Grupo | Arquivos/função |
|---|---|
| Firmware | `ControleESP32.ino` e `sensors_v4.h`; o helper copia ambos e o teste C++ inclui o header |
| Entradas Python | `poc_raspberry/main.py` para pipeline/API/modos de diagnóstico; `preview.py` para reconhecimento local com janela |
| Configurações | `poc_raspberry/config.yaml` para pipeline; `config.preview.yaml` para reconhecimento de garrafas com o modelo novo |
| Núcleo | Todos os `.py` em `poc_raspberry/core/`: câmera, detector, decisão, contratos, estados, serial, configuração, logs, telemetria, diagnósticos e exports de pacote |
| API atual | `poc_raspberry/api/status_server.py` e `api/templates/dashboard.html`; não confundir esse template com o HTML do servidor antigo |
| Simulação | Todos os `.py` de `poc_raspberry/mock/`; usados pelo pipeline, preview ou runner independente |
| Modelos do preview | `coco_ssd.names`, `ssd_mobilenet_v1_coco_2017_11_17.pb`, `ssd_mobilenet_v1_coco_2017_11_17.pbtxt` |
| Testes | `poc_raspberry/tests/test_decision.py`, `test_v4.py`, `test_consolidation.py`, `sensors_v4_test.cpp` e `__init__.py` |
| Dependências | Os três `requirements*.txt`: base Raspberry, desenvolvimento headless e GUI. São perfis diferentes, não cópias obsoletas |
| Ferramentas | `tools/compile_firmware.py`, `verify_api.py`, `benchmark_mock.py` |
| Serviço atual | `configs/ecoflutuador-v4.service`; é um exemplo de instalação que exige ajuste de caminhos/usuário/configuração |
| Documentação atual | `README.md`, `README_TESTE.md`, `poc_raspberry/README.md`, `PINAGEM_V4.md`, `SENSORES_V4.md`, `docs/OPERACAO_V4.md` |
| Documentação histórica útil | `docs/AUDITORIA_V4.md`, `docs/RESULTADO_V4.md`, evidências correspondentes |
| Regras locais | `.gitignore`; complementa o `.gitignore` da raiz |

Apesar do nome `poc_raspberry`, essa pasta contém a implementação atual. Não é
uma POC descartável. Renomeá-la exige atualizar documentação, ferramentas,
testes e caminhos de instalação; não é necessário para a primeira limpeza.

## Arquivos já ausentes

O Git já registra como removidos: `ControleESP32V2`, `ESTRUTURA_V4.md`, `diario`,
`servidor.py`, `servidorSliders.py` e `servidorUnificado.py`. Não estão presentes
para serem apagados novamente. Não foram restaurados nem removidos nesta revisão.
As alterações anteriores do usuário e das etapas desta conversa foram preservadas.

## Validação da limpeza inicial

Foi criada uma cópia temporária do V4, omitindo os nove arquivos de legado/vazio/
placeholder e os seis arquivos de build, sem copiar o venv nem caches. Nessa cópia:

- 88 testes passaram, incluindo a compilação/execução nativa do teste C++ de sensores.
- `tools/verify_api.py` verificou HTTP 200 em `/`, `/health`, `/status`, `/telemetry`,
  `/history`, `/diagnostics` e encerramento correto.
- `preview.py --mock --image ... --output ...` detectou a garrafa sintética e salvou
  a imagem anotada, usando o mesmo caminho de renderização da janela.

A cópia temporária foi descartada ao final. Não houve uso de UART física,
acionamento de motores, instalação/desativação de serviços ou exclusão de arquivos
do projeto. A simulação não valida instalações externas em um Raspberry.

## Organização sugerida

1. Remover o legado identificado e os artefatos gerados, mantendo o arquivo histórico.
2. Atualizar o README principal para distinguir claramente pipeline, dashboard de dados
   e preview gráfico: hoje o pipeline continua com o perfil de modelo antigo.
3. Migrar o pipeline para o modelo compatível, incluindo pré-processamento, e validar
   antes de remover os três arquivos antigos de modelos.
4. Reunir documentos históricos em `docs/`, atualizando os links; manter os guias de
   operação e reconhecimento facilmente acessíveis.
5. Manter os caminhos Python e firmware atuais na primeira limpeza. Uma reorganização
   em `raspberry/` e `firmware/` pode ser feita depois, com atualização das referências.

Esta revisão identifica candidatos e dependências. Não executa a limpeza proposta.
