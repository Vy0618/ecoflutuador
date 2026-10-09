"""Injeta eventos e resultados na V4 existente para verificar a referência.

Não implementa o novo ciclo na V4.5 nem abre câmera, modelo, UART ou HTTP.
"""
import json
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "V4" / "poc_raspberry"))

import numpy as np
from main import Pipeline
from core.contracts import Detection
from core.decision import DecisionConfig, DecisionEngine


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    pipeline = Pipeline({"recognition": {"confirmation_s": 0.1,
        "detection_timeout_s": 2, "window_s": 15}}, "mock")
    pipeline._decision = DecisionEngine(DecisionConfig(confirmation_frames=3,
        loss_timeout_s=0.5, hysteresis_fraction=0.04))
    pipeline._serial = Mock()
    pipeline._serial.send_command.return_value = True
    pipeline._detector = Mock()
    image = np.zeros((240, 320, 3), dtype=np.uint8)

    def inject(now, line=None, detections=None, frame_id=None):
        with patch("main.time.monotonic", return_value=now):
            if line:
                pipeline._on_serial_response(line)
            if detections is not None:
                pipeline._detector.detect.return_value = detections
                pipeline._process_frame(image, frame_id)
            else:
                pipeline._service(now)
        output = {"time_s": now, "input": line or ("frame" if detections is not None else "tick"),
                  "state": pipeline.controller.state.value,
                  "command": pipeline._decision.details()["current_command"]}
        print(json.dumps(output, ensure_ascii=False))
        return output

    check(inject(0, "EVENT:START:1")["state"] == "CONFIRMING", "START não confirmou")
    check(inject(0.1)["state"] == "RECOGNIZING", "Reconhecimento não ativou")
    for frame_id, now in enumerate((0.11, 0.21, 0.31), 1):
        result = inject(now, detections=[Detection([10, 0, 20, 30], "bottle", 0.9)], frame_id=frame_id)
        check(result["command"] == ("a" if frame_id == 3 else "s"), "Confirmação de 3 frames")
    check(inject(0.4, detections=[], frame_id=4)["command"] == "a", "Perda breve não tolerada")
    check(inject(0.82, detections=[], frame_id=5)["command"] == "s", "STOP após perda")
    check(inject(2.32, "EVENT:START:1")["state"] == "WAITING", "Timeout sem alvo")
    check(inject(2.4, "EVENT:START:1")["state"] == "WAITING", "START alto rearmou")
    inject(2.5, "EVENT:START:0")
    check(inject(2.6, "EVENT:START:1")["state"] == "CONFIRMING", "Novo START não rearmou")
    inject(2.71)
    invalid = 'TEL:{"schema":1,"ultrasonic":{"enabled":true,"valid":false,"calibrated":true,"start_detected":true}}'
    result = inject(2.8, invalid)
    check(result["state"] == "FAULT" and result["command"] == "s", "Sensor inválido não parou")

    # Isola a histerese da máquina operacional; três novos frames por mudança.
    decision = DecisionEngine(DecisionConfig(confirmation_frames=3, hysteresis_fraction=0.04))
    frame_id = 0
    for center, expected in ((90, "a"), (110, "a"), (130, "w")):
        for _ in range(3):
            frame_id += 1
            decision.decide([Detection([center - 10, 0, 20, 30], "bottle", 0.9, frame_id)],
                            320, now=frame_id / 10)
        check(decision.details()["current_command"] == expected, "Histerese incorreta")
        print(json.dumps({"test": "hysteresis", "center_x": center, "command": expected}))

    # A janela máxima precisa expirar mesmo com detecções constantes.
    from core.state import RecognitionController
    controller = RecognitionController(confirmation_s=0, window_s=15)
    controller.start_event(True, 0)
    controller.tick(0)
    for now in range(1, 15):
        controller.detection(True, now)
        controller.tick(now)
    controller.tick(15)
    check(controller.state.value == "WAITING", "Janela máxima não expirou")
    print(json.dumps({"test": "window", "time_s": 15, "state": controller.state.value}))
    print(json.dumps({"result": "PASS", "hardware": False, "reference": "V4"}))


if __name__ == "__main__":
    run()
