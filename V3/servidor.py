from flask import Flask, Response, request
import cv2
import serial
import threading
import time

app = Flask(__name__)

ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)

log_comandos = []
log_lock = threading.Lock()

def registrar(msg):
    with log_lock:
        timestamp = time.strftime("%H:%M:%S")
        log_comandos.append(f"[{timestamp}] {msg}")
        if len(log_comandos) > 20:
            log_comandos.pop(0)

def ler_serial():
    while True:
        try:
            if ser.in_waiting > 0:
                linha = ser.readline().decode('utf-8').strip()
                if linha.startswith("CMD_OK:"):
                    cmd = linha.split(":")[1]
                    registrar(f"ESP32 confirmou: '{cmd}'")
        except:
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
    body{text-align:center;font-family:sans-serif;background:#111;color:#fff;}
    button{width:90px;height:90px;margin:5px;font-size:18px;background:#222;color:#fff;border:2px solid #555;border-radius:8px;}
    button:active{background:#444;}
    #cam{width:100%;max-width:640px;border:2px solid #333;margin:10px auto;display:block;}
    #log{background:#1a1a1a;border:1px solid #333;border-radius:8px;max-width:640px;margin:10px auto;padding:10px;text-align:left;font-size:12px;font-family:monospace;height:150px;overflow-y:auto;color:#0f0;}
  </style>
</head>
<body>
  <h2>EcoFlutuador</h2>
  <img id="cam" src="/stream">
  <div style="margin-top:10px;">
    <button onclick="mover('w')">Frente</button><br>
    <button onclick="mover('a')">Esq</button>
    <button onclick="mover('s')">Parar</button>
    <button onclick="mover('d')">Dir</button><br>
    <button onclick="mover('q')">Gir E</button>
    <button onclick="mover('e')">Gir D</button>
  </div>
  <div id="log">Aguardando comandos...</div>
  <script>
    function mover(cmd){
      fetch('/move?cmd='+cmd)
        .then(r=>r.json())
        .then(()=>atualizarLog());
    }
    function atualizarLog(){
      fetch('/log')
        .then(r=>r.json())
        .then(data=>{
          const d=document.getElementById('log');
          d.innerHTML=data.log.join('<br>');
          d.scrollTop=d.scrollHeight;
        });
    }
    setInterval(atualizarLog,1000);
  </script>
</body>
</html>'''

@app.route('/stream')
def stream():
    return Response(gerar_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/move')
def move():
    cmd = request.args.get('cmd','')
    if cmd in ['w','a','s','d','q','e']:
        ser.write(cmd.encode())
        registrar(f"Enviado: '{cmd}'")
        return {'status':'enviado','cmd':cmd}
    return {'status':'erro'}

@app.route('/log')
def log():
    with log_lock:
        return {'log': list(log_comandos)}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
