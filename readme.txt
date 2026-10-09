ECOFLUTUADOR — CONTEXTO E PREPARAÇÃO DO AMBIENTE
================================================

O EcoFlutuador integra Raspberry Pi, câmera e ESP32 para controle de dois
motores e reconhecimento de objetos. A expansão inclui sensores, navegação
automática e acompanhamento da operação.

VERSÕES

V3/: base histórica com controle manual, câmera, sliders de potência e
variantes de reconhecimento automático. Contém servidores monolíticos,
caminhos fixos e dependência de hardware na inicialização.

V4/: expansão modular com sensores, estados operacionais, comunicação serial,
simulação, testes e dashboard de dados. Há funcionalidades incompletas e
validação física pendente. O ponto de entrada atual é
V4/poc_raspberry/main.py. Consulte V4/README.md e V4/docs/OPERACAO_V4.md.

v4.5/: cópia inicial da V3, destinada ao desenvolvimento incremental de um
produto mais organizado. Ainda não contém a reconstrução proposta.
Respeite estas maiúsculas/minúsculas: os caminhos diferem em Linux.

AMBIENTE VIRTUAL — SEMPRE CRIAR E INSTALAR AS DEPENDÊNCIAS

Em cada máquina, crie seu próprio venv. Não copie a .venv de outra máquina
e não a envie ao Git. Antes de executar qualquer programa, ative o ambiente
e instale as dependências a partir da raiz deste projeto.

Ambiente de referência verificado: Linux x86_64 e Python 3.12.
requirements.txt usa requirements-lock.txt para fixar também as dependências
indiretas. A disponibilidade dos pacotes varia por sistema e arquitetura.

Linux/macOS:

    python3.12 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip check

Windows (PowerShell, Python 3.12 instalado):

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip check

Se a ativação estiver bloqueada no PowerShell, use diretamente
.\.venv\Scripts\python.exe nos comandos de instalação e execução.
No Linux, se o módulo venv estiver ausente, instale o pacote python3-venv
ou python3.12-venv correspondente ao Python da distribuição.
Para sair do ambiente: deactivate.

VERIFICAÇÕES SEM HARDWARE

Com o ambiente ativado, a partir da raiz:

    python -c "import cv2, numpy, flask, serial, yaml; print('Dependências OK')"
    python -m unittest discover -s V4/poc_raspberry/tests -v
    python V4/poc_raspberry/mock/run_mock.py --frames 100 --fps 10 --quiet

A suíte inclui testes C++ nativos: g++ precisa estar disponível para executá-los.
No Debian/Ubuntu, ele é fornecido pelo pacote build-essential.
O runner mock acima não abre câmera, UART física nem servidor HTTP.
Os 88 testes e uma execução simulada passaram no ambiente de referência.
Simulação não comprova o funcionamento de sensores, câmera ou motores reais.

OPENCV E RASPBERRY PI

A instalação padrão usa opencv-python-headless. Ela permite captura de câmera,
processamento e streaming web, mas não janelas gráficas cv2.imshow, usadas pelo
experimento legado object-ident.py. Para usar esse experimento em um desktop:

    python -m pip uninstall opencv-python-headless
    python -m pip install opencv-python==5.0.0.93

Esse perfil gráfico não foi validado nesta configuração. Não instale os dois
pacotes OpenCV simultaneamente; reinstalar requirements.txt retorna ao perfil
headless, portanto remova antes o pacote gráfico nessa troca.

Na Raspberry, pacotes pip podem não ter wheels para a versão do Python/SO.
Como alternativa, use OpenCV/NumPy da distribuição e crie o venv com
--system-site-packages. Consulte as instruções específicas da V4 e registre as
versões desse ambiente: ele não corresponde automaticamente ao lock x86_64.
O backend CSI requer Picamera2/libcamera próprios do Raspberry Pi OS;
eles não estão no requirements.txt geral. O padrão atual da V4 é câmera USB.

CONFIGURAÇÃO E HARDWARE

Na V4, copie V4/poc_raspberry/config.yaml para config.local.yaml na mesma pasta
e indique explicitamente o arquivo com --config. Ajuste câmera, porta serial,
modelo e porta HTTP. Esse arquivo particular é ignorado pelo Git.

V3 e v4.5 ainda têm configurações no código: revise /dev/ttyUSB0, câmera,
caminhos /home/eco/Desktop/Object_Detection_Files e serviços antes de executar.
Criar config.local.yaml não altera o funcionamento desses servidores antigos.
Portas seriais são diferentes no Windows (COMx), Linux e macOS. A captura V4L2
dos legados é específica de Linux; instalar dependências não a torna portátil.
No Linux, verifique acesso aos dispositivos serial e vídeo (normalmente grupos
dialout e video). Alterações de grupos exigem nova sessão do usuário.

Firmware precisa do core Arduino ESP32 e ESP32Servo; a V4 também requer
TinyGPSPlus. Esses componentes não são instalados pelo pip. Para a V4, consulte
V4/PINAGEM_V4.md e o helper V4/tools/compile_firmware.py. Registre versões do
core, bibliotecas e placa ao validar uma compilação.

LIMITAÇÕES ATUAIS

O par de pesos/configuração do detector legado em V4/poc_raspberry/models
não carrega no ambiente verificado: erro Const input blob for weights not found.
Instalar requirements.txt não corrige esse modelo. A V3 e a cópia v4.5 apontam
para modelos em caminhos externos, que também precisam ser disponibilizados.
Os modelos existentes não fornecem todas as classes propostas para a V4.

Não execute várias versões simultaneamente: elas podem disputar câmera,
serial e porta 8080. Os servidores legados abrem hardware ao serem iniciados
ou importados. Não use a execução deles como teste de instalação.
Os binários em V4/build/firmware são artefatos antigos; não demonstram uma
compilação do código atual. Serviços systemd existentes também exigem revisão
de caminhos e usuário antes da instalação.

REPLICAÇÃO E CONTROLE DE VERSÕES

Versione código, documentação, requirements.txt e requirements-lock.txt.
O .gitignore exclui venvs, caches, builds, logs, configuração local e perfis
NetworkManager, que podem conter credenciais. Ele não remove arquivos já
versionados; revise o conteúdo antes de publicar o repositório.
O .gitattributes padroniza finais de linha dos arquivos de texto.

Após atualizar dependências, execute as verificações novamente e atualize o
lock usando um ambiente limpo dedicado ao projeto. Ao transferir a instalação,
registre SO, arquitetura, versão do Python, modelo usado e versões do firmware.
Modelos e componentes físicos devem acompanhar esse registro; o venv é recriado.
