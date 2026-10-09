"""Ponto de entrada: monta os componentes e gerencia sua execução."""
import signal
from config import Config
from controller import Controller
from web import create_app


def main():
    config = Config.from_env()
    controller = Controller(config)
    app = create_app(controller)

    def terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        controller.start()
        app.run(host=config.host, port=config.port, debug=False,
                threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
