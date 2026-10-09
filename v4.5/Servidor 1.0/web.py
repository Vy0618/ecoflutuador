"""HTTP: traduz solicitações da interface para operações do controlador."""
from pathlib import Path
from flask import Flask, Response, render_template, request, send_from_directory

ROOT = Path(__file__).resolve().parent


def create_app(controller):
    app = Flask(__name__, template_folder=str(ROOT), static_folder=None)
    app.extensions["ecoflutuador"] = controller

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/static/<path:filename>", endpoint="static")
    def static_file(filename):
        # Os assets existentes compartilham pasta com código e configuração.
        if filename not in {"script.js", "style.css"}:
            return {"status": "erro"}, 404
        return send_from_directory(ROOT, filename)

    @app.get("/stream")
    def stream():
        return Response(controller.camera.frames(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/set_modo")
    def set_mode():
        try:
            return {"modo_auto": controller.set_mode(request.args.get("auto", "0") == "1")}
        except Exception as exc:
            controller.log.register(f"ERRO modo: {exc}")
            return {"status": "erro", "msg": str(exc)}, 500

    @app.get("/move")
    def move():
        command = request.args.get("cmd", "")
        try:
            controller.move(command)
            return {"status": "enviado", "cmd": command}
        except PermissionError as exc:
            return {"status": "erro", "msg": str(exc)}, 403
        except ValueError as exc:
            return {"status": "erro", "msg": str(exc)}, 400
        except Exception as exc:
            controller.log.register(f"ERRO serial: {exc}")
            return {"status": "erro", "msg": str(exc)}, 500

    @app.get("/power")
    def power():
        try:
            motor = int(request.args.get("motor", 0))
            value = int(request.args.get("val", 30))
            value = controller.power(motor, value)
            return {"status": "ok", "motor": motor, "potencia": value}
        except ValueError as exc:
            return {"status": "erro", "msg": str(exc)}, 400
        except Exception as exc:
            controller.log.register(f"ERRO potência: {exc}")
            return {"status": "erro", "msg": str(exc)}, 500

    @app.get("/log")
    def log():
        return {"log": controller.log.snapshot(), "modo_auto": controller.automatic}

    return app
