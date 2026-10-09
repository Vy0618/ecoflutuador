from flask import Flask, Response, request
import cv2
import serial
import threading
import time

app = Flask(__name__)

ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)

log_comandos = []
log_lock = threading.Lock()
potencia1 = 30
potencia2 = 30

# --- Modo automático ---
modo_auto = False
modo_lock = threading.Lock()

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

class Camera:
    def __init__(self):
        self.cam = cv2.VideoCapture(0, cv2.CAP_V4L2)
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.cam.set(cv2.CAP_PROP_FPS, 10)
        self.cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame_raw  = None   # frame sem anotações (para detecção)
        self.frame_jpeg = None   # frame codificado para stream
        self.lock = threading.Lock()
        threading.Thread(target=self._capturar, daemon=True).start()

    def _capturar(self):
        while True:
            sucesso, frame = self.cam.read()
            if sucesso:
                with self.lock:
                    self.frame_raw = frame.copy()

                with modo_lock:
                    auto = modo_auto

                if auto:
                    frame, _ = detectar(frame)

                _, buffer = cv2.imencode('.jpg', frame,
                                        [cv2.IMWRITE_JPEG_QUALITY, 50])
                with self.lock:
                    self.frame_jpeg = buffer.tobytes()
            time.sleep(0.05)

    def get_frame(self):
        with self.lock:
            return self.frame_jpeg

    def get_raw(self):
        with self.lock:
            return self.frame_raw.copy() if self.frame_raw is not None else None

camera = Camera()

# Loop autônomo — roda em background quando modo_auto=True
def loop_autonomo():
    ultimo_cmd = None
    while True:
        with modo_lock:
            auto = modo_auto
        if auto:
            frame = camera.get_raw()
            if frame is not None:
                _, objectInfo = detectar(frame.copy())
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
    return '''<!DOCTYPE html>
<html>
<head>
  <title>EcoFlutuador</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; }
    body {
      text-align:center; font-family:sans-serif;
      background:#111; color:#fff; margin:0; padding:10px;
    }

    button {
      width:90px; height:90px; margin:5px; font-size:18px;
      background:#222; color:#fff; border:2px solid #555;
      border-radius:8px; cursor:pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    button:active { background:#444; }
    button:disabled { opacity:0.3; cursor:not-allowed; }

    #cam {
      width:100%; max-width:640px;
      border:2px solid #333; margin:10px auto; display:block;
    }

    #log {
      background:#1a1a1a; border:1px solid #333; border-radius:8px;
      max-width:640px; margin:10px auto; padding:10px;
      text-align:left; font-size:12px; font-family:monospace;
      height:120px; overflow-y:auto; color:#0f0;
    }

    /* --- Botão de modo --- */
    #modo-wrap {
      max-width:640px; margin:12px auto;
    }
    #btn-modo {
      width:100%; height:54px; font-size:16px; font-weight:bold;
      border-radius:10px; border:2px solid #555;
      background:#222; color:#fff;
      letter-spacing:1px;
      transition: background 0.25s, border-color 0.25s, color 0.25s;
    }
    #btn-modo.auto {
      background:#0a3a0a; border-color:#0f0; color:#0f0;
    }
    #btn-modo.auto::before { content:"🤖  "; }
    #btn-modo:not(.auto)::before { content:"🕹️  "; }

    /* --- Potência --- */
    .power-box {
      max-width:640px; margin:12px auto;
      background:#1a1a1a; border:1px solid #333;
      border-radius:8px; padding:14px;
      display:flex; gap:20px;
    }
    .motor-ctrl { flex:1; }
    .motor-ctrl h3 { margin:0 0 8px; font-size:14px; color:#aaa; }
    .motor-ctrl .val { font-size:24px; font-weight:bold; }
    #val1 { color:#f90; }
    #val2 { color:#0cf; }
    input[type=range] { width:100%; margin:6px 0; }
    #slider1 { accent-color:#f90; }
    #slider2 { accent-color:#0cf; }
    .status { font-size:11px; color:#666; min-height:16px; }

    .link-btn {
      max-width:640px; margin:8px auto;
      background:#1a1a1a; border:1px solid #444;
      border-radius:8px; padding:10px;
      display:flex; align-items:center; justify-content:center; gap:10px;
    }
    .link-btn label { font-size:13px; color:#aaa; }
    .link-btn input[type=checkbox] { width:20px; height:20px; accent-color:#9f0; cursor:pointer; }

    /* controles desabilitados no modo auto */
    #controles { transition: opacity 0.3s; }
    #controles.bloqueado { opacity:0.3; pointer-events:none; }

    /* badge de modo no stream */
    .cam-wrap {
      position:relative; max-width:640px; margin:10px auto;
    }
    #cam { margin:0; width:100%; }
    #badge-modo {
      position:absolute; top:8px; left:8px;
      padding:3px 10px; border-radius:20px;
      font-size:11px; font-weight:bold; letter-spacing:1px;
      background:#111c; color:#aaa; border:1px solid #555;
      transition: background 0.3s, color 0.3s, border-color 0.3s;
    }
    #badge-modo.auto {
      background:#0a3a0ac0; color:#0f0; border-color:#0f0;
    }
  </style>
</head>
<body>
  <h2>EcoFlutuador</h2>

  <div class="cam-wrap">
    <img id="cam" src="/stream">
    <div id="badge-modo">MANUAL</div>
  </div>

  <!-- Botão de modo -->
  <div id="modo-wrap">
    <button id="btn-modo" onclick="alternarModo()">MODO MANUAL</button>
  </div>

  <!-- Potência — sempre visível -->
  <div class="power-box">
    <div class="motor-ctrl">
      <h3>Motor 1 (Esquerdo)</h3>
      <div class="val" id="val1">30%</div>
      <input type="range" id="slider1" min="0" max="100" value="30">
      <div class="status" id="status1">—</div>
    </div>
    <div class="motor-ctrl">
      <h3>Motor 2 (Direito)</h3>
      <div class="val" id="val2">30%</div>
      <input type="range" id="slider2" min="0" max="100" value="30">
      <div class="status" id="status2">—</div>
    </div>
  </div>

  <div class="link-btn">
    <label for="linkado">Sincronizar motores</label>
    <input type="checkbox" id="linkado" checked>
  </div>

  <!-- Controles manuais -->
  <div id="controles" style="margin-top:10px;">
    <button onclick="mover(\'w\')">Frente</button><br>
    <button onclick="mover(\'a\')">Esq</button>
    <button onclick="mover(\'s\')">Parar</button>
    <button onclick="mover(\'d\')">Dir</button><br>
    <button onclick="mover(\'q\')">Gir E</button>
    <button onclick="mover(\'e\')">Gir D</button>
  </div>

  <div id="log">Aguardando comandos...</div>

  <script>
    const s1 = document.getElementById('slider1');
    const s2 = document.getElementById('slider2');
    const v1 = document.getElementById('val1');
    const v2 = document.getElementById('val2');
    const st1 = document.getElementById('status1');
    const st2 = document.getElementById('status2');
    const linkado = document.getElementById('linkado');
    const btnModo = document.getElementById('btn-modo');
    const controles = document.getElementById('controles');
    const badge = document.getElementById('badge-modo');

    let timer1 = null, timer2 = null;
    let modoAuto = false;

    // ---------- Alternar modo ----------
    function alternarModo() {
      modoAuto = !modoAuto;
      fetch('/set_modo?auto=' + (modoAuto ? '1' : '0'))
        .then(r => r.json())
        .then(d => {
          atualizarUIMode(d.modo_auto);
        })
        .catch(() => {
          modoAuto = !modoAuto; // reverte se falhar
        });
    }

    function atualizarUIMode(auto) {
      modoAuto = auto;
      if (auto) {
        btnModo.textContent = 'MODO AUTOMÁTICO';
        btnModo.classList.add('auto');
        badge.textContent = 'AUTO';
        badge.classList.add('auto');
        controles.classList.add('bloqueado');
      } else {
        btnModo.textContent = 'MODO MANUAL';
        btnModo.classList.remove('auto');
        badge.textContent = 'MANUAL';
        badge.classList.remove('auto');
        controles.classList.remove('bloqueado');
      }
    }

    // ---------- Sliders de potência ----------
    s1.addEventListener('input', () => {
      v1.textContent = s1.value + '%';
      if (linkado.checked) { s2.value = s1.value; v2.textContent = s1.value + '%'; }
      st1.textContent = 'Aguardando...';
      clearTimeout(timer1);
      timer1 = setTimeout(() => {
        enviarPotencia(1, s1.value, st1);
        if (linkado.checked) enviarPotencia(2, s2.value, st2);
      }, 300);
    });

    s2.addEventListener('input', () => {
      v2.textContent = s2.value + '%';
      if (linkado.checked) { s1.value = s2.value; v1.textContent = s2.value + '%'; }
      st2.textContent = 'Aguardando...';
      clearTimeout(timer2);
      timer2 = setTimeout(() => {
        enviarPotencia(2, s2.value, st2);
        if (linkado.checked) enviarPotencia(1, s1.value, st1);
      }, 300);
    });

    function enviarPotencia(motor, val, statusEl) {
      statusEl.textContent = 'Enviando...';
      fetch(`/power?motor=${motor}&val=${val}`)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => {
          statusEl.textContent = data.status === 'ok' ? `✓ ${val}%` : '✗ Erro';
        })
        .catch(() => { statusEl.textContent = '✗ Falha'; });
    }

    // ---------- Comandos manuais ----------
    function mover(cmd) {
      if (modoAuto) return;
      fetch('/move?cmd=' + cmd)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(() => atualizarLog())
        .catch(err => console.warn('Erro ao mover:', err));
    }

    // ---------- Log ----------
    function atualizarLog() {
      fetch('/log')
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => {
          const d = document.getElementById('log');
          d.innerHTML = data.log.join('<br>');
          d.scrollTop = d.scrollHeight;
        })
        .catch(err => console.warn('Erro no log:', err));
    }

    setInterval(atualizarLog, 1000);
  </script>
</body>
</html>'''

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

@app.route('/log')
def log():
    try:
        with log_lock:
            return {'log': list(log_comandos)}
    except Exception as e:
        return {'status': 'erro', 'msg': str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)