from flask import Flask, Response, render_template, request
import cv2
import serial
import threading
import time

# -------------------------------------------------------

app = Flask(
    __name__,
    template_folder='.',
    static_folder='.',
    static_url_path='/static'
)

ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)

log_comandos = []
log_lock = threading.Lock()
potencia1 = 30
potencia2 = 30

# --- Modo automático ---
modo_auto = False
modo_lock = threading.Lock()

# -------------------------------------------------------

# Configuração do modelo de detecção (Código 2)
classNames = []
classFile = "/home/eco/Desktop/Object_Detection_Files/coco.names"
with open(classFile, "rt") as f:
    classNames = f.read().rstrip("\n").split("\n")

configPath  = "/home/eco/Desktop/Object_Detection_Files/ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt"
weightsPath = "/home/eco/Desktop/Object_Detection_Files/frozen_inference_graph.pb"

net = cv2.dnn_DetectionModel(weightsPath, configPath)
net.setInputSize(320, 320)
net.setInputScale(1.0 / 127.5)
net.setInputMean((127.5, 127.5, 127.5))
net.setInputSwapRB(True)

# Objetos-alvo que o modo automático perseguirá
ALVOS = ['bottle']

# -------------------------------------------------------

def detectar(img, thres=0.45, nms=0.2):
    """Roda detecção e retorna (img_anotada, objectInfo)."""
    classIds, confs, bbox = net.detect(img, confThreshold=thres, nmsThreshold=nms)
    objectInfo = []
    if len(classIds) != 0:
        for classId, confidence, box in zip(classIds.flatten(), confs.flatten(), bbox):
            className = classNames[classId - 1]
            if className in ALVOS:
                objectInfo.append([box, className])
                cv2.rectangle(img, box, color=(0, 255, 0), thickness=2)
                cv2.putText(img, className.upper(),
                            (box[0] + 10, box[1] + 30),
                            cv2.FONT_HERSHEY_COMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(img, str(round(confidence * 100, 1)) + "%",
                            (box[0] + 10, box[1] + 58),
                            cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 200, 0), 1)
    return img, objectInfo
   

def decidir_acao(objectInfo, largura_frame=320):
    """
    Lógica de navegação autônoma baseada na posição do objeto detectado.
    Divide o frame em três zonas horizontais: esquerda / centro / direita.
    Retorna o caractere de comando ou None.

    Para fins de alteração do sistema devemos manter a lógica de distância 
    porém alterar o formato de decidir ação... Ele deve receber formatos json
    para decisão, sem processamento de imagem ativo no raspberry PI
    """
    if not objectInfo:
        return None  # nada detectado → fica parado

    # Pega o objeto de maior área (mais próximo)
    melhor = max(objectInfo, key=lambda o: o[0][2] * o[0][3])
    box = melhor[0]  # x, y, w, h
    cx = box[0] + box[2] // 2  # centro horizontal do objeto

    zona = largura_frame // 3
    if cx < zona:
        return 'a'          # objeto à esquerda → vira esquerda
    elif cx > 2 * zona:
        return 'd'          # objeto à direita  → vira direita
    else:
        return 'w'          # objeto no centro  → avança

# -------------------------------------------------------

class Camera:
    def __init__(self):
        """
        Nessa parte precisa ter resize da identificação (alterar pixels
        e fps) e parar de rodar a imagem... Precisamos que ele corte processamento
        ativo da imagem and send only data to the decision system
        """
        self.cam = cv2.VideoCapture(0, cv2.CAP_V4L2)
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.cam.set(cv2.CAP_PROP_FPS, 10)
        self.cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.frame_raw  = None   # frame sem anotações (para detecção)
        self.frame_jpeg = None   # frame codificado para stream
        self.objectInfo = []

        self.lock = threading.Lock()
        threading.Thread(target=self._capturar, daemon=True).start()

    def _capturar(self):
        while True:
            sucesso, frame = self.cam.read()
            if sucesso:
               
                with modo_lock:
                    auto = modo_auto

                objectInfo = []

                if auto:
                    frame, objectInfo = detectar(frame)

                _, buffer = cv2.imencode('.jpg', frame,
                                        [cv2.IMWRITE_JPEG_QUALITY, 50])
                with self.lock:
                    self.frame_raw = frame.copy()
                    self.objectInfo = objectInfo
                    self.frame_jpeg = buffer.tobytes()
            time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.frame_jpeg

    def get_raw(self):
        with self.lock:
            return self.frame_raw.copy() if self.frame_raw is not None else None

    def get_objects(self):
         with self.lock:
             return list(self.objectInfo)

# -------------------------------------------------------
camera = Camera()
# -------------------------------------------------------

# Loop autônomo — roda em background quando modo_auto=True
def loop_autonomo():
    ultimo_cmd = None
    while True:
        with modo_lock:
            auto = modo_auto
        if auto:
                objectInfo = camera.get_objects()
                cmd = decidir_acao(objectInfo)
                if cmd != ultimo_cmd:
                    if cmd:
                        try:
                            ser.write((cmd + '\n').encode())
                            registrar(f"[AUTO] Enviado: '{cmd}'")
                        except Exception as e:
                            registrar(f"[AUTO] ERRO serial: {e}")
                    else:
                        try:
                            ser.write(('s\n').encode())
                            registrar("[AUTO] Nenhum alvo — parando")
                        except Exception:
                            pass
                    ultimo_cmd = cmd
        else:
            ultimo_cmd = None  # reseta ao sair do modo auto
        time.sleep(0.15)

threading.Thread(target=loop_autonomo, daemon=True).start()

# -------------------------------------------------------

def gerar_frames():
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' +
                   frame + b'\r\n')
        time.sleep(0.05)

# -------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/set_modo')
def set_modo():
    global modo_auto
    val = request.args.get('auto', '0')
    with modo_lock:
        modo_auto = (val == '1')
        estado = modo_auto
    registrar(f"Modo alterado para: {'AUTOMÁTICO' if estado else 'MANUAL'}")
    if not estado:
        # Para os motores ao sair do modo automático
        try:
            ser.write(('s\n').encode())
        except Exception:
            pass
    return {'modo_auto': estado}

@app.route('/stream')
def stream():
    return Response(gerar_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# -------------------------------------------------------

@app.route('/move')
def move():
    with modo_lock:
        auto = modo_auto
    if auto:
        return {'status': 'erro', 'msg': 'em modo automático'}, 403
    cmd = request.args.get('cmd', '')
    if cmd in ['w', 'a', 's', 'd', 'q', 'e']:
        try:
            ser.write((cmd + '\n').encode())
            registrar(f"Enviado: '{cmd}'")
            return {'status': 'enviado', 'cmd': cmd}
        except Exception as e:
            registrar(f"ERRO serial: {e}")
            return {'status': 'erro', 'msg': str(e)}, 500
    return {'status': 'erro', 'msg': 'comando inválido'}, 400

# -------------------------------------------------------

@app.route('/power')
def power():
    global potencia1, potencia2
    try:
        motor = int(request.args.get('motor', 0))
        val   = int(request.args.get('val', 30))
        val   = max(0, min(100, val))
        if motor not in [1, 2]:
            return {'status': 'erro', 'msg': 'motor inválido'}, 400
        if motor == 1:
            potencia1 = val
        else:
            potencia2 = val
        msg = f"P{motor}{val:03d}\n"
        ser.write(msg.encode())
        registrar(f"M{motor} → {val}%")
        return {'status': 'ok', 'motor': motor, 'potencia': val}
    except Exception as e:
        registrar(f"ERRO potência: {e}")
        return {'status': 'erro', 'msg': str(e)}, 500

# -------------------------------------------------------

@app.route('/log')
def log():
    try:
        with log_lock:
            return {'log': list(log_comandos)}
    except Exception as e:
        return {'status': 'erro', 'msg': str(e)}, 500

def registrar(msg):
    with log_lock:
        timestamp = time.strftime("%H:%M:%S")
        log_comandos.append(f"[{timestamp}] {msg}")
        if len(log_comandos) > 20:
            log_comandos.pop(0)

def ler_serial():
    global ser
    while True:
        try:
            if ser.in_waiting > 0:
                linha = ser.readline().decode('utf-8').strip()
                if linha.startswith("CMD_OK:"):
                    cmd = linha.split(":")[1]
                    registrar(f"ESP32 confirmou: '{cmd}'")
                elif linha.startswith("PWR_OK:"):
                    partes = linha.split(":")
                    registrar(f"Potência M{partes[1]} confirmada: {partes[2]}%")
        except serial.SerialException as e:
            registrar(f"Serial perdida: {e} — reconectando...")
            time.sleep(2)
            try:
                ser.close()
                ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
                registrar("Serial reconectada!")
            except Exception as e2:
                registrar(f"Falha ao reconectar: {e2}")
        except Exception:
            pass
        time.sleep(0.05)

threading.Thread(target=ler_serial, daemon=True).start()

# -------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)

    
