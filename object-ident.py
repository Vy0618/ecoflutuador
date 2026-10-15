#!/usr/bin/env python3
"""Reconhecimento local de garrafas com SSD MobileNet V3."""
import argparse
import os
from pathlib import Path
import sys
import time

import cv2

from camera import LatestFrameCamera, WebcamConfig
from config import CONFIG_FILE, load_config
from detection.ssd_mobilenet_detector import SsdMobileNetDetector
from image_processing import prepare_frame, restore_coordinates
from regions import regions_for_frame
from command_log import CommandLog
from navigation import COMMANDS, Navigation, record_navigation
from esp32_link import Esp32Link


WINDOW = "V4.1 - SSD MobileNet V3 - Garrafas"


def create_detector(config):
    model = config["ssd_mobilenet"]
    return SsdMobileNetDetector(
        model_path=model["model_path"], config_path=model["config_path"],
        labels_path=model["labels_path"], confidence_threshold=model["confidence_threshold"],
        input_width=model["input_width"], input_height=model["input_height"],
        allowed_classes=model["detection_types"],
    )


def detect_frame(detector, frame, config):
    processed = prepare_frame(frame, config["image_processing"])
    return restore_coordinates(detector.detect(processed), processed.shape, frame.shape)


def annotate(frame, detections, bottom_zone_ratio=0.8, navigation=None):
    image = frame.copy()
    height, width = image.shape[:2]
    regions = regions_for_frame(width, height, bottom_zone_ratio)
    line_y = regions.line_y
    zone_width = regions.first_x
    color = (0, 230, 255)
    cv2.line(image, (0, line_y), (width - 1, line_y), color, 2)
    for x in (zone_width, 2 * zone_width):
        cv2.line(image, (x, 0), (x, line_y), color, 2)
    scale = .6 * min(1, width / 640)
    for label, center_x, text_y in (
        (f"ESQUERDA [{COMMANDS['esquerda']}]", zone_width // 2, 25),
        (f"MEIO [{COMMANDS['meio']}]", zone_width + zone_width // 2, 25),
        (f"DIREITA [{COMMANDS['direita']}]", (2 * zone_width + width) // 2, 25),
        (f"BAIXO [{COMMANDS['baixo']}]", width // 2, line_y + (height - line_y) // 2),
    ):
        text_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
        position = (max(0, center_x - text_width // 2), min(height - 4, text_y))
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox
        selected = navigation is not None and navigation.selected is detection
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 3 if selected else 1)
        label = f"{detection.class_name.upper()} {detection.confidence:.0%}"
        if selected:
            label += " ALVO"
            cv2.circle(image, detection.centroid, 5, (0, 255, 0), -1)
        label_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
        position = (max(0, min(x1, width - label_width - 4)), max(45, y1 - 8))
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, label, position, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 255, 0), 1, cv2.LINE_AA)
    if navigation is not None:
        status = f"COMANDO: {navigation.command} | REGIAO: {(navigation.region or 'sem alvo').upper()}"
        position = (8, height - 10)
        for ink, thickness in (((0, 0, 0), 3), (color, 1)):
            cv2.putText(image, status, position, cv2.FONT_HERSHEY_SIMPLEX, scale, ink, thickness, cv2.LINE_AA)
        if navigation.approach_complete:
            cv2.putText(image, "APROXIMACAO ENCERRADA", (8, height - 32),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", type=Path, default=CONFIG_FILE)
    parser.add_argument("--camera-index", type=int)
    parser.add_argument("--serial-port", help="Porta do ESP32, por exemplo /dev/ttyUSB0")
    parser.add_argument("--output", help="Saida ESP32: oled (padrao) ou motors; com --image, aceita o caminho de saida antigo")
    sensor = parser.add_mutually_exclusive_group()
    sensor.add_argument("--ultrasonic", dest="ultrasonic", action="store_true", default=None,
                        help="Exige ativacao pelo HC-SR04 (padrao com motors)")
    sensor.add_argument("--no-ultrasonic", dest="ultrasonic", action="store_false",
                        help="Opera continuamente, sem sensor (padrao com oled)")
    parser.add_argument("--duration", type=float, help="Encerra apos N segundos")
    parser.add_argument("--image", type=Path, help="Reconhece imagem sem abrir webcam")
    parser.add_argument("--image-output", type=Path, help="Caminho da imagem anotada; exige --image")
    parser.add_argument("--log-file", type=Path, default=Path(__file__).resolve().parent / "logs" / "recognition.jsonl",
                        help="Arquivo de registros; cada registro tambem aparece no terminal")
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--display", dest="display", action="store_true",
                         help="Exibe o video com as linhas (padrao)")
    display.add_argument("--no-display", dest="display", action="store_false",
                         help="Executa sem janela, somente quando solicitado")
    parser.set_defaults(display=True)
    args = parser.parse_args()
    image_output = args.image_output
    if args.image:
        if args.output and image_output:
            parser.error("Com --image, escolha --image-output ou o antigo --output")
        image_output = image_output or (Path(args.output) if args.output else None)
        if image_output is None:
            parser.error("Use --image com --image-output (ou --output)")
    else:
        if image_output is not None:
            parser.error("--image-output exige --image")
        if args.output not in (None, "oled", "motors"):
            parser.error("--output deve ser oled ou motors")
    if args.image and args.serial_port:
        parser.error("--serial-port exige reconhecimento pela webcam")
    if not args.serial_port and (args.ultrasonic is not None or (args.output and not args.image)):
        parser.error("Os argumentos de modo exigem --serial-port")
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration deve ser positivo")
    if args.camera_index is not None and args.camera_index < 0:
        parser.error("--camera-index deve ser nao negativo")
    camera = None
    window_created = False
    log = None
    navigation = None
    motor_link = None
    mode = "serial" if args.serial_port else "terminal"
    try:
        config = load_config(args.config)
        detector = create_detector(config)
        navigation = Navigation(config["display"]["bottom_zone_ratio"],
                                allowed_classes=config["ssd_mobilenet"]["detection_types"],
                                **config["navigation"])
        log = CommandLog(args.log_file)
        if args.image:
            frame = cv2.imread(str(args.image))
            if frame is None:
                raise ValueError(f"Nao foi possivel ler {args.image}")
            detections = detect_frame(detector, frame, config)
            result = navigation.update(detections, frame.shape[1], frame.shape[0])
            record_navigation(log, result, detections)
            if not cv2.imwrite(str(image_output), annotate(frame, detections, config["display"]["bottom_zone_ratio"], result)):
                raise OSError(f"Nao foi possivel salvar {image_output}")
            print(f"Garrafas detectadas: {len(detections)}")
            return 0
        show = args.display
        if show:
            gui = next((line for line in cv2.getBuildInformation().splitlines()
                        if line.strip().startswith("GUI:")), "GUI: NONE")
            if gui.split(":", 1)[1].strip() == "NONE":
                raise RuntimeError("Instale opencv-python com GUI usando requirements.txt")
            if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                raise RuntimeError("Abra em um terminal da sessao grafica, ou use --no-display")
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            window_created = True
            cv2.resizeWindow(WINDOW, config["camera"]["width"], config["camera"]["height"])
            cv2.moveWindow(WINDOW, 40, 40)
            cv2.waitKey(1)
        if args.camera_index is not None:
            config["camera"]["device_index"] = args.camera_index
        camera_settings = WebcamConfig(**config["camera"])
        device = camera_settings.open_camera()
        camera = LatestFrameCamera(device, target_fps=camera_settings.fps)
        if args.serial_port:
            motor_link = Esp32Link(args.serial_port, output=args.output or "oled", ultrasonic=args.ultrasonic)
            log.record(evento="serial", porta=args.serial_port, baud=Esp32Link.BAUD,
                       iniciar=motor_link.iniciar, saida=motor_link.output,
                       ultrassonico=motor_link.ultrasonic, modo=mode)
        log.record(evento="camera", configuracao=str(args.config.resolve()),
                   fps_configurado=camera_settings.fps,
                   fps_reportado_camera=device.get(cv2.CAP_PROP_FPS),
                   intervalo_inferencia_ms=config["detection_interval_ms"],
                   video_habilitado=show, modo=mode)
        interval = config["detection_interval_ms"] / 1000
        start = time.monotonic()
        next_detection = 0
        detections = []
        last_shape = None
        result = None
        while args.duration is None or time.monotonic() - start < args.duration:
            frame = camera.read()
            now = time.monotonic()
            if motor_link:
                motor_link.poll()
                if motor_link.activation_changed:
                    navigation = Navigation(config["display"]["bottom_zone_ratio"],
                                            allowed_classes=config["ssd_mobilenet"]["detection_types"],
                                            **config["navigation"])
                    detections = []
                    result = navigation.stop()
                    next_detection = 0
                    last_shape = None
                    log.record(evento="ultrassonico", iniciar=motor_link.iniciar, comando="s", modo=mode)
                    motor_link.activation_changed = False
                if not motor_link.iniciar:
                    detections = []
                    result = navigation.stop()
            if (not motor_link or motor_link.iniciar) and (now >= next_detection or frame.shape != last_shape):
                detections = detect_frame(detector, frame, config)
                if motor_link:
                    motor_link.poll()
                if not motor_link or (motor_link.iniciar and not motor_link.activation_changed):
                    result = navigation.update(detections, frame.shape[1], frame.shape[0])
                    if motor_link:
                        motor_link.send(result.command)
                        if not motor_link.iniciar or motor_link.activation_changed:
                            detections = []
                            result = navigation.stop()
                    record_navigation(log, result, detections, mode=mode)
                else:
                    detections = []
                    result = navigation.stop()
                next_detection = now + interval
                last_shape = frame.shape
            if show:
                cv2.imshow(WINDOW, annotate(frame, detections, config["display"]["bottom_zone_ratio"], result))
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        if log:
            log.record(evento="erro", mensagem=str(exc), comando="s", modo=mode)
        print(f"Falha no reconhecimento: {exc}", file=sys.stderr)
        return 1
    finally:
        if motor_link:
            try:
                motor_link.close()
            except Exception as exc:
                if log:
                    log.record(evento="erro", mensagem=str(exc), comando="s", modo=mode)
                print(f"Falha ao confirmar parada do ESP32: {exc}", file=sys.stderr)
        if log:
            if navigation:
                record_navigation(log, navigation.stop(), [], event="encerramento", mode=mode)
            log.close()
        if camera:
            camera.close()
        if window_created:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    sys.exit(main())
