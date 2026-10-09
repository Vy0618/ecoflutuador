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

class Camera:
    def __init__(self):
        self.cam = cv2.VideoCapture(0, cv2.CAP_V4L2)
        self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        self.cam.set(cv2.CAP_PROP_FPS, 10)
        self.cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame = None
        self.lock = threading.Lock()
        threading.Thread(target=self._capturar, daemon=True).start()

    def _capturar(self):
        while True:
            sucesso, frame = self.cam.read()
            if sucesso:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                with self.lock:
                    self.frame = buffer.tobytes()
            time.sleep(0.05)

    def get_frame(self):
        with self.lock:
            return self.frame

camera = Camera()

def gerar_frames():
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' +
                   frame + b'\r\n')
        time.sleep(0.05)

@app.route('/')
def index():
    return '''<!DOCTYPE html>
<html>
<head>
  <title>EcoFlutuador</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; }
    body { text-align:center; font-family:sans-serif; background:#111; color:#fff; margin:0; padding:10px; }
    button { width:90px; height:90px; margin:5px; font-size:18px; background:#222; color:#fff; border:2px solid #555; border-radius:8px; }
    button:active { background:#444; }
    #cam { width:100%; max-width:640px; border:2px solid #333; margin:10px auto; display:block; }
    #log { background:#1a1a1a; border:1px solid #333; border-radius:8px; max-width:640px; margin:10px auto; padding:10px; text-align:left; font-size:12px; font-family:monospace; height:120px; overflow-y:auto; color:#0f0; }

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
  </style>
</head>
<body>
  <h2>EcoFlutuador</h2>
  <img id="cam" src="/stream">

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

  <div style="margin-top:10px;">
    <button onclick="mover('w')">Frente</button><br>
    <button onclick="mover('s')">Parar</button>
    <button onclick="mover('a')">Gir E</button>
    <button onclick="mover('d')">Gir D</button>
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

    let timer1 = null, timer2 = null;

    s1.addEventListener('input', () => {
      v1.textContent = s1.value + '%';
      if (linkado.checked) {
        s2.value = s1.value;
        v2.textContent = s1.value + '%';
      }
      st1.textContent = 'Aguardando...';
      clearTimeout(timer1);
      timer1 = setTimeout(() => {
        enviarPotencia(1, s1.value, st1);
        if (linkado.checked) enviarPotencia(2, s2.value, st2);
      }, 300);
    });

    s2.addEventListener('input', () => {
      v2.textContent = s2.value + '%';
      if (linkado.checked) {
        s1.value = s2.value;
        v1.textContent = s2.value + '%';
      }
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
          statusEl.textContent = data.status === 'ok'
            ? `✓ ${val}%`
            : '✗ Erro';
        })
        .catch(() => { statusEl.textContent = '✗ Falha'; });
    }

    function mover(cmd) {
      fetch('/move?cmd=' + cmd)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(() => atualizarLog())
        .catch(err => console.warn('Erro ao mover:', err));
    }

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

@app.route('/stream')
def stream():
    return Response(gerar_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/move')
def move():
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
        # Formato "P1045\n" ou "P2070\n"
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
