#!/usr/bin/env python3
"""Visualizacao continua da decisao V4, sem serial, API ou motores."""
import argparse
import logging
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from core.camera import Camera, CameraConfig
from core.config import load_config
from core.decision import DecisionConfig, DecisionEngine
from core.detector import Detector, ModelConfig
from mock.camera_mock import MockCamera, MockCameraConfig
from mock.detector_mock import MockDetector


WINDOW = "EcoFlutuador V4 - reconhecimento"
ACTIONS = {"a": "ESQUERDA", "w": "FRENTE", "d": "DIREITA", "s": "PARADO"}


def annotate(frame, detections, decision, automatic=True, synthetic=False, inference_ms=0):
    """Renderiza uma copia; linhas usam exatamente as fronteiras da decisao."""
    image = frame.copy()
    height, width = image.shape[:2]
    text_scale = .48 * min(1, width / 640)
    zone = decision.get_zones(width)["zone_width"]
    command = decision.details()["current_command"]
    for index, (label, key) in enumerate((("ESQUERDA [a]", "a"), ("FRENTE [w]", "w"), ("DIREITA [d]", "d"))):
        color = (0, 230, 255) if command == key else (210, 210, 210)
        position = (index * zone + 8, 24)
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, text_scale, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, text_scale, color, 1, cv2.LINE_AA)
    for x in (zone, 2 * zone):
        cv2.line(image, (x, 30), (x, height), (0, 230, 255), 2)
    for detection in detections:
        x, y, w, h = map(int, detection.bbox)
        selected = detection is decision.selected
        if detection.class_name in decision.config.fauna_classes:
            color = (0, 80, 255)
        elif detection.class_name in decision.config.target_classes:
            color = (0, 220, 0)
        else:
            color = (170, 170, 170)
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 3 if selected else 1)
        label = f"{detection.class_name} {detection.confidence:.0%}" + (" ALVO" if selected else "")
        position = (max(0, x), max(42, y - 8))
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, text_scale, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, text_scale, color, 1, cv2.LINE_AA)
        if selected:
            center = (x + w // 2, y + h // 2)
            cv2.circle(image, center, 5, color, -1)
            cv2.line(image, (width // 2, height - 1), center, color, 2)
    panel = np.zeros((126, width, 3), dtype=np.uint8)
    mode = "AUTOMATICO" if automatic else "PAUSADO"
    detector = "SIMULACAO DE COR" if synthetic else "SSD COCO"
    lines = [f"{mode} | {ACTIONS[command]} [{command}] | {detector}",
             decision.reason, f"Inferencia: {inference_ms:.0f} ms | Sem envio a motores",
             "ESPACO: automatico/pausa | R: reiniciar | Q/ESC: sair"]
    for index, line in enumerate(lines):
        cv2.putText(panel, line, (10, 24 + index * 28), cv2.FONT_HERSHEY_SIMPLEX, text_scale, (235, 235, 235), 1, cv2.LINE_AA)
    return np.vstack((image, panel))


def make_detector(config, synthetic):
    if synthetic:
        return MockDetector()
    model = config["model"]
    return Detector(ModelConfig(weights=model["weights"], config=model["config"],
                                target_classes=model.get("target_classes", ["bottle"]),
                                class_filter=model.get("target_classes", ["bottle"]),
                                classes=model["classes"], input_size=tuple(model["input_size"]),
                                input_scale=model.get("input_scale", 1 / 127.5),
                                input_mean=tuple(model.get("input_mean", [127.5] * 3)),
                                conf_threshold=model.get("conf_threshold", .45),
                                nms_threshold=model.get("nms_threshold", .2)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", default=str(Path(__file__).with_name("config.preview.yaml")))
    parser.add_argument("--mock", action="store_true", help="Objeto verde sintetico; nao reconhece objetos reais")
    parser.add_argument("--camera-index", type=int, help="Indice da webcam (padrao: 0)")
    parser.add_argument("--duration", type=float, help="Encerra apos N segundos")
    parser.add_argument("--image", type=Path, help="Reconhece uma imagem sem abrir camera ou janela")
    parser.add_argument("--output", type=Path, help="Destino da imagem anotada; exige --image")
    args = parser.parse_args()
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration deve ser positivo")
    if bool(args.image) != bool(args.output):
        parser.error("Use --image e --output juntos")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    camera = None
    window_created = False
    try:
        config = load_config(args.config)
        decision = DecisionEngine(DecisionConfig(**config["decision"]))
        detector = make_detector(config, args.mock)
        if args.image:
            frame = cv2.imread(str(args.image))
            if frame is None:
                raise ValueError(f"Nao foi possivel ler {args.image}")
            began = time.perf_counter()
            detections = detector.detect(frame)
            inference_ms = (time.perf_counter() - began) * 1000
            # Imagem unica nao fornece as tres capturas exigidas para confirmar direcao.
            decision.decide(detections, frame.shape[1])
            if not cv2.imwrite(str(args.output), annotate(frame, detections, decision, synthetic=args.mock, inference_ms=inference_ms)):
                raise OSError(f"Nao foi possivel salvar {args.output}")
            print([d.to_result() for d in detections])
            return 0
        gui_line = next((line for line in cv2.getBuildInformation().splitlines() if line.strip().startswith("GUI:")), "GUI: NONE")
        if gui_line.split(":", 1)[1].strip() == "NONE":
            raise RuntimeError("OpenCV sem GUI. Instale requirements-gui.txt conforme README_TESTE.md")
        if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise RuntimeError("Abra em um terminal da sessao grafica local para exibir a janela")
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        window_created = True
        cv2.resizeWindow(WINDOW, 960, 900)
        cam = config["camera"]
        camera = MockCamera(MockCameraConfig(width=cam["width"], height=cam["height"], fps=cam["fps"])) if args.mock else Camera(CameraConfig(
            backend=cam["backend"], index=args.camera_index if args.camera_index is not None else cam["index"],
            width=cam["width"], height=cam["height"], fps=cam["fps"]))
        if not camera.start():
            raise RuntimeError("Nao foi possivel abrir a camera; verifique indice e outros processos usando webcam")
        automatic = True
        start = last_frame = time.monotonic()
        frame_id = 0
        previous_command = None
        while args.duration is None or time.monotonic() - start < args.duration:
            frame = camera.get_frame()
            if frame is not None:
                last_frame = time.monotonic()
                frame_id += 1
                began = time.perf_counter()
                detections = detector.detect(frame) if automatic else []
                inference_ms = (time.perf_counter() - began) * 1000
                for detection in detections:
                    detection.frame_id = frame_id
                if automatic:
                    decision.decide(detections, frame.shape[1])
                else:
                    decision.stop("Reconhecimento pausado")
                command = decision.details()["current_command"]
                if command != previous_command:
                    logging.info("Decisao: %s [%s] - %s", ACTIONS[command], command, decision.reason)
                    previous_command = command
                cv2.imshow(WINDOW, annotate(frame, detections, decision, automatic, args.mock, inference_ms))
            elif time.monotonic() - last_frame > cam.get("timeout_s", 2):
                raise RuntimeError("Camera sem novos frames")
            key = cv2.waitKey(10) & 0xFF
            if key in (27, ord("q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord(" "):
                automatic = not automatic
                decision.reset()
            elif key == ord("r"):
                decision.reset()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        logging.error("Visualizacao falhou: %s", exc)
        return 1
    finally:
        if camera:
            camera.stop()
        if window_created:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    sys.exit(main())
