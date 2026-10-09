#!/usr/bin/env python3
"""
EcoFlutuador POC - Main entry point.
Runs the autonomous navigation pipeline: Camera -> Detector -> Decision -> Serial.
Modes:
  --mock       : Simulated camera + serial (no hardware)
  --dry-run    : Real camera + detector + decision, NO serial commands sent
  --real       : Real camera + detector + decision + serial to ESP32
"""
import sys
import os
import argparse
import time
import logging
import signal
import json
import queue
import yaml
from typing import Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config
from core.logging_config import setup_logging
from mock.detector_mock import MockDetector
from core.camera import Camera, CameraConfig, list_cameras
from core.detector import Detector, ModelConfig
from core.decision import DecisionEngine, DecisionConfig
from core.serial_link import SerialLink, SerialConfig, parse_response
from core.state import DetectionState, RecognitionController, OperationalState
from api.status_server import StatusServer
from mock.camera_mock import MockCamera, MockCameraConfig
from mock.serial_mock import MockSerialLink, MockSerialConfig


class Pipeline:
    """Main processing pipeline."""

    def __init__(self, config: dict, mode: str):
        self.config = config
        self.mode = mode
        self._logger = logging.getLogger(__name__)
        self._running = False
        self._camera = None
        self._detector = None
        self._decision = None
        self._serial = None
        self._status_server = None
        self._frame_count = 0
        self._start_time = time.time()
        self._last_fps_log = 0
        self._frames_since_log = 0
        self._target_fps = config.get("performance", {}).get("target_fps", 10)
        self._last_telemetry = None
        self._telemetry_time = None
        self._responses = queue.Queue(maxsize=256)
        op = config.get("recognition", {})
        self.controller = RecognitionController(op.get("confirmation_s", 0.1), op.get("detection_timeout_s", 2.0), op.get("window_s", 15.0))
        self._telemetry_timeout_s = op.get("telemetry_timeout_s", 3.0)
        self._last_sent = None
        self._net = {}
        self._started_monotonic = time.monotonic()
        self._simulation_high = False
        self._response_overflow = False
        self._last_heartbeat = 0.0
        self._last_generation = None
        self._capture_id = 0
        self._last_frame_time = time.monotonic()
        self._last_state_log = None
        self._last_state_log_time = 0.0
        self._last_runtime_state = None

    def setup(self) -> bool:
        try:
            return self._setup()
        except (Exception, SystemExit) as exc:
            self.controller.fault(str(exc))
            self._logger.error("Setup failed: %s", exc)
            self.shutdown()
            return False

    def _setup(self) -> bool:
        """Initialize all components based on mode."""
        cam_cfg = self.config.get("camera", {})
        model_cfg = self.config.get("model", {})
        decision_cfg = self.config.get("decision", {})
        serial_cfg = self.config.get("serial", {})
        api_cfg = self.config.get("api", {})
        perf_cfg = self.config.get("performance", {})

        # Camera
        if self.mode == "mock":
            self._camera = MockCamera(MockCameraConfig(
                width=cam_cfg.get("width", 320),
                height=cam_cfg.get("height", 240),
                fps=cam_cfg.get("fps", 10)
            ))
        else:
            self._camera = Camera(CameraConfig(
                backend=cam_cfg.get("backend", "V4L2"),
                index=cam_cfg.get("index", 0),
                width=cam_cfg.get("width", 320),
                height=cam_cfg.get("height", 240),
                fps=cam_cfg.get("fps", 10),
                buffer_size=cam_cfg.get("buffer_size", 1),
                picamera2_format=cam_cfg.get("picamera2", {}).get("format", "RGB888"),
                picamera2_transform=cam_cfg.get("picamera2", {}).get("transform", {})
            ))

        if not self._camera.start():
            self._logger.error("Failed to start camera")
            return False

        # Detector (only for real/dry-run modes)
        backend = model_cfg.get("backend", "legacy_ssd")
        if self.mode == "real" and backend == "mock":
            raise ValueError("Mock detector forbidden in production")
        if self.mode == "mock" or backend == "mock":
            self._detector = MockDetector()
        elif ":" in backend:
            from importlib import import_module
            module, factory = backend.split(":", 1)
            self._detector = getattr(import_module(module), factory)(model_cfg)
            if not callable(getattr(self._detector, "detect", None)):
                raise TypeError("Detector factory must provide detect(frame)")
        elif backend != "legacy_ssd":
            raise ValueError("Detector backend not installed: " + backend)
        else:
            try:
                self._detector = Detector(ModelConfig(
                    weights=model_cfg.get("weights", "models/frozen_inference_graph.pb"),
                    config=model_cfg.get("config", "models/ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt"),
                    classes=model_cfg.get("classes", "models/coco.names"),
                    input_size=tuple(model_cfg.get("input_size", [320, 320])),
                    conf_threshold=model_cfg.get("conf_threshold", 0.45),
                    nms_threshold=model_cfg.get("nms_threshold", 0.2),
                    target_classes=model_cfg.get("target_classes", ["bottle"])
                ))
            except FileNotFoundError as e:
                self._logger.error(str(e))
                self._camera.stop()
                return False
            except Exception as e:
                self._logger.error(f"Detector initialization failed: {e}")
                self._camera.stop()
                return False

        # Decision engine
        decision_cfg = self.config.get("decision", {})
        # frame_width is dynamic — passed from actual frame later
        self._decision = DecisionEngine(DecisionConfig(
            target_classes=tuple(decision_cfg.get("target_classes", ["bottle", "plastic_bottle", "plastic_bag"])),
            fauna_classes=tuple(decision_cfg.get("fauna_classes", ["fish", "turtle", "bird"])),
            fauna_priority=decision_cfg.get("fauna_priority", True),
            confidence_threshold=decision_cfg.get("confidence_threshold", .45),
            zones=decision_cfg.get("zones", 3),
            default_command=decision_cfg.get("default_command", "s"),
            send_only_on_change=True,
            confirmation_frames=decision_cfg.get("confirmation_frames", 3),
            loss_timeout_s=decision_cfg.get("loss_timeout_s", 0.5),
            hysteresis_fraction=decision_cfg.get("hysteresis_fraction", 0.04)
        ))

        # Serial (only for real mode)
        if self.mode == "real":
            self._serial = SerialLink(SerialConfig(
                port=serial_cfg.get("port", "/dev/serial0"),
                baudrate=serial_cfg.get("baudrate", 115200),
                timeout=serial_cfg.get("timeout", 1.0),
                reconnect_delay=serial_cfg.get("reconnect_delay", 2.0),
                auto_detect=serial_cfg.get("auto_detect", True)
            ), on_response=self._on_serial_response)

            if not self._serial.start():
                self._logger.error("Failed to start serial communication")
                self._camera.stop()
                return False
            self._logger.info("Serial communication started (REAL MODE - commands will be sent to ESP32)")
        elif self.mode == "dry-run":
            self._logger.info("DRY-RUN MODE: Camera + Detection + Decision active, NO serial commands sent")
        else:  # mock
            self._serial = MockSerialLink(MockSerialConfig(response_delay=0.001), on_response=self._on_serial_response)
            self._serial.start()
            self._logger.info("MOCK MODE: Simulated camera + serial")

        # Status API (optional)
        if api_cfg.get("enabled", True):
            self._status_server = StatusServer(
                host=api_cfg.get("host", "0.0.0.0"),
                port=api_cfg.get("port", 8080),
                device_id=self.config.get("telemetry", {}).get("device_id", "eco-01"),
                telemetry_timeout_s=self._telemetry_timeout_s
            )
            try:
                self._status_server.start()
            except (Exception, SystemExit) as exc:
                self._logger.error("Observability API unavailable: %s", exc)
                self._status_server = None
            if self._last_telemetry is not None:
                self._status_server.update_telemetry(self._last_telemetry)

        self._running = True
        self._started_monotonic = time.monotonic()
        self._start_time = time.time()
        self._last_fps_log = self._start_time
        return True

    def _on_serial_response(self, line: str) -> None:
        # Serial reader queues; only the main loop mutates operational state.
        try:
            self._responses.put_nowait((time.monotonic(), line))
        except queue.Full:
            self._response_overflow = True
            self._logger.error("Serial response queue overflow")

    def _service(self, now=None):
        now = time.monotonic() if now is None else now
        if self.mode == "real" and self._serial:
            generation = getattr(self._serial, "generation", 0)
            if isinstance(generation, int) and generation != self._last_generation:
                self._last_generation = generation
                self._last_sent = None
                self._telemetry_time = None
                self.controller.fault("Nova sessao UART; aguardando TEL e novo START")
                self._safe_stop(self.controller.last_error)
        if self._response_overflow:
            self._response_overflow = False
            while not self._responses.empty():
                try:
                    self._responses.get_nowait()
                except queue.Empty:
                    break
            self.controller.fault("Fila serial excedida; aguardando nova telemetria")
            self._safe_stop(self.controller.last_error)
        for _ in range(256):
            try:
                received_at, line = self._responses.get_nowait()
                received_at = min(received_at, now)
            except queue.Empty:
                break
            if now-received_at > self._telemetry_timeout_s:
                self.controller.fault("Mensagem UART expirada na fila")
                self._safe_stop(self.controller.last_error)
                continue
            parsed = parse_response(line)
            if parsed is None:
                self.controller.last_error = "Resposta serial invalida"
                continue
            kind = parsed["type"]
            if kind == "telemetry":
                previous_uptime = (self._last_telemetry or {}).get("uptime_ms")
                new_uptime = parsed["data"].get("uptime_ms")
                if isinstance(previous_uptime, (int,float)) and isinstance(new_uptime,(int,float)) and new_uptime < previous_uptime:
                    self.controller.fault("ESP32 reboot/uptime reset")
                    self._last_sent = None
                    self._safe_stop(self.controller.last_error)
                self._last_telemetry, self._telemetry_time = parsed["data"], received_at
                tel = self._last_telemetry
                self._net = dict(tel.get("net", self._net))
                invalid_ultrasonic = tel.get("ultrasonic", {}).get("enabled", False) and (
                    not tel["ultrasonic"].get("valid", False) or tel["ultrasonic"].get("calibrated") is False)
                lease_required = self.mode == "real" and self.config.get("serial", {}).get("require_control_lease", False)
                lease_compatible = (tel.get("protocol_version") == "1.1" and tel.get("control_timeout_ms") == 1500
                    and type(tel.get("uptime_ms")) is int
                    and isinstance(tel.get("ultrasonic"), dict)
                    and "start_detected" in tel["ultrasonic"] and "valid" in tel["ultrasonic"])
                if lease_required and not lease_compatible:
                    self.controller.fault("Firmware sem lease de controle compativel")
                    self._safe_stop(self.controller.last_error)
                elif invalid_ultrasonic:
                    self.controller.fault("HC-SR04 invalido ou calibrando")
                    self._safe_stop(self.controller.last_error)
                elif self.controller.state == OperationalState.FAULT:
                    self.controller.recover()
                    # Recovery never converts a held START into a fresh edge.
                    self.controller.start_high = bool(tel.get("ultrasonic", {}).get("start_detected", tel.get("start", {}).get("detected", False)))
                start = tel.get("ultrasonic", {}).get("start_detected", tel.get("start", {}).get("detected"))
                if start is not None:
                    self.controller.start_event(start, now)
                if self._status_server:
                    self._status_server.update_telemetry(tel)
            elif kind == "start_event":
                self._logger.info("UART START", extra={"event": parsed})
                self.controller.start_event(parsed["detected"], now)
                if not parsed["detected"]:
                    self._safe_stop("START liberado")
            elif kind == "net_event":
                event = parsed["event"]
                self._net["last_event"] = event
                if event == "BLOCKED": self._net["blocked"] = True
                elif event == "PASS": self._net["blocked"] = False
                elif event == "FULL_SUSPECTED": self._net["full_suspected"] = True
                elif event == "CLEAR": self._net.update(blocked=False, full_suspected=False)
            elif kind in {"boot", "error"}:
                self._last_sent = None
                self.controller.fault(parsed.get("message", "ESP32 reiniciou; aguardando telemetria"))
                self._safe_stop(self.controller.last_error)
        if self.mode == "real":
            age = now-(self._telemetry_time if self._telemetry_time is not None else self._started_monotonic)
            if not self._serial or not self._serial.connected or age > self._telemetry_timeout_s:
                self.controller.fault("Serial offline ou telemetria expirada")
        self.controller.tick(now)
        if not self.controller.active:
            self._safe_stop("Estado " + self.controller.state.value)
        if self.mode == "real" and self._serial and self._serial.connected and self._last_sent not in (None, "s") and self.controller.active:
            if now-self._last_heartbeat >= self.config.get("serial", {}).get("heartbeat_s", .5):
                if not self._serial.send_heartbeat(self._last_sent):
                    self.controller.fault("Falha heartbeat UART")
                    self._safe_stop(self.controller.last_error)
                self._last_heartbeat = now
        if self.controller.state.value != self._last_runtime_state:
            self._last_runtime_state = self.controller.state.value
            self._logger.info("Estado operacional", extra={"event": self.runtime_status(now)})
        if self._status_server:
            self._status_server.update_runtime(self.runtime_status(now))

    def runtime_status(self, now=None):
        now = time.monotonic() if now is None else now
        age = None if self._telemetry_time is None else max(0, int((now-self._telemetry_time)*1000))
        return {"uptime_s": round(now-self._started_monotonic, 2),
                "mode": self.mode,
                "model_version": self.config.get("model", {}).get("version"),
                "detector_backend": "mock" if self.mode == "mock" else self.config.get("model", {}).get("backend", "legacy_ssd"),
                "operational_state": self.controller.state.value,
                "recognition_active": self.controller.active,
                "serial_connected": bool(self.mode == "real" and self._serial and self._serial.connected
                                         and age is not None and age <= self._telemetry_timeout_s*1000),
                "telemetry_age_ms": age,
                "camera_backend": "MOCK" if self.mode == "mock" else self.config.get("camera", {}).get("backend", "V4L2"),
                "ultrasonic": (self._last_telemetry or {}).get("ultrasonic", {}),
                "net": self._net, "environmental": (self._last_telemetry or {}).get("water", {}),
                "last_error": self.controller.last_error,
                "decision_details": self._decision.details() if self._decision else {}}

    def _send(self, cmd):
        if self.mode in ("real", "mock") and self._serial and cmd != self._last_sent:
            if self._serial.send_command(cmd):
                self._last_sent = cmd
                self._last_heartbeat = time.monotonic()
                self._logger.info("Comando enviado", extra={"event": {"command": cmd, "mode": self.mode}})
            else:
                self.controller.fault("Falha no envio serial")
                if self._decision: self._decision.stop("Falha no envio serial")

    def _safe_stop(self, reason):
        if self._decision:
            self._decision.stop(reason)
        self._send("s")

    def _process_frame(self, frame, frame_id=None) -> Optional[DetectionState]:
        """Process a single frame: detect -> decide -> (send)."""
        self._service()
        if not self.controller.active:
            return DetectionState.empty()
        inference_start = time.perf_counter()

        # Detection never contains navigation policy.
        detections = self._detector.detect(frame) if self._detector else self._mock_detect(frame)
        self._capture_id += 1
        effective_id = frame_id if frame_id is not None else self._capture_id
        for detection in detections:
            detection.frame_id = effective_id
        elapsed_ms = (time.perf_counter()-inference_start)*1000
        if elapsed_ms > self.config.get("performance", {}).get("max_inference_ms", 1000):
            self.controller.fault("Inferencia excedeu prazo de controle")
            self._safe_stop(self.controller.last_error)
            return DetectionState.empty()

        # Check STOP received while inference was running before sending movement.
        self._service()
        if not self.controller.active:
            return DetectionState.empty()
        self.controller.detection(bool(detections), time.monotonic())
        inference_ms = (time.perf_counter() - inference_start) * 1000
        self._last_inference_ms = inference_ms

        # Decision — pass actual frame width for proportional zones
        frame_width = frame.shape[1]
        decision = self._decision.decide(detections, frame_width=frame_width)
        cmd_to_send = decision if decision else self._decision._last_command

        # Build state
        if self._decision.selected is not None:
            best = self._decision.selected
            state = DetectionState.from_detection(
                box=best.bbox,
                class_name=best.class_name,
                confidence=best.confidence,
                decision=cmd_to_send or "s",
                inference_ms=inference_ms,
                fps=self._current_fps(),
                frame_width=frame.shape[1],
                frame_height=frame.shape[0]
            )
        else:
            state = DetectionState.empty(
                timestamp=time.time(),
                fps=self._current_fps()
            )
            state.decision = cmd_to_send or "s"

        self._logger.debug("Reconhecimento", extra={"event": {"frame_id": effective_id,
            "detections": [d.to_result() for d in detections], "command": cmd_to_send,
            "latency_ms": round(inference_ms, 2)}})
        # Send command only if changed
        self._send(cmd_to_send or "s")
        if self.controller.state == OperationalState.FAULT:
            self._safe_stop(self.controller.last_error)
            state = DetectionState.empty()

        return state

    def _mock_detect(self, frame) -> list:
        """Compatibility shim for the deterministic mock runner."""
        return MockDetector().detect(frame)

    def _current_fps(self) -> float:
        """Calculate current FPS."""
        elapsed = time.time() - self._start_time
        return self._frame_count / elapsed if elapsed > 0 else 0

    def _log_state(self, state: DetectionState) -> None:
        """Log state as JSON to stdout."""
        now = time.monotonic()
        key = (self.controller.state.value, state.detected, state.object, state.decision)
        if key != self._last_state_log or now-self._last_state_log_time >= self.config.get("telemetry", {}).get("interval_s", 5):
            self._logger.info("Estado", extra={"event": state.to_json()})
            self._last_state_log, self._last_state_log_time = key, now

    def _log_fps(self) -> None:
        """Log FPS periodically."""
        now = time.time()
        if now - self._last_fps_log >= 5.0:
            fps = self._frames_since_log / (now - self._last_fps_log)
            self._logger.info(f"FPS: {fps:.1f} | Total frames: {self._frame_count} | Inference: {getattr(self, '_last_inference_ms', 0):.1f}ms")
            self._last_fps_log = now
            self._frames_since_log = 0

    def run(self) -> int:
        """Main processing loop."""
        self._logger.info(f"Starting pipeline in {self.mode.upper()} mode")
        self._logger.info(f"Target FPS: {self._target_fps}")

        try:
            while self._running:
                loop_start = time.perf_counter()

                self._service()
                simulation = self.config.get("simulation", {})
                elapsed_s = time.monotonic()-self._started_monotonic
                if self.mode != "real" and simulation.get("start_after_s") is not None:
                    high = simulation["start_after_s"] <= elapsed_s < simulation.get("clear_after_s", float("inf"))
                    if high != self._simulation_high:
                        self._simulation_high = high
                        self._on_serial_response("EVENT:START:" + str(int(high)))
                if self.config.get("duration_s") and elapsed_s >= self.config["duration_s"]:
                    break
                # Get frame
                frame = self._camera.get_frame()
                if frame is not None:
                    self._last_frame_time = time.monotonic()
                elif time.monotonic()-self._last_frame_time > self.config.get("camera", {}).get("timeout_s", 1):
                    raise RuntimeError("Camera sem novos frames")
                if frame is None:
                    state = DetectionState.empty()
                    if self.controller.active:
                        # No new capture is not evidence of an absent object.
                        # Camera timeout/recognition timeout enforce safety.
                        state.decision = self._decision.details()["current_command"]
                    if self._status_server:
                        self._status_server.update_state(state)
                        self._status_server.update_runtime(self.runtime_status())
                    time.sleep(1.0/self._target_fps)
                    continue

                self._frame_count += 1
                self._frames_since_log += 1

                # Process frame
                state = self._process_frame(frame, getattr(self._camera, "last_frame_id", None))

                # Log state
                self._log_state(state)

                # Update status API
                if self._status_server:
                    self._status_server.update_state(state)
                    self._status_server.update_runtime(self.runtime_status())

                # FPS logging
                self._log_fps()

                # Maintain target FPS
                elapsed = time.perf_counter() - loop_start
                target_interval = 1.0 / self._target_fps
                sleep_time = target_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            self._logger.info("Interrupted by user (Ctrl+C)")
        except Exception as e:
            self.controller.fault(str(e))
            self._safe_stop(str(e))
            self._logger.error(f"Pipeline error: {e}", exc_info=True)
            return 1
        finally:
            self.shutdown()

        return 0

    def shutdown(self) -> None:
        """Clean shutdown of all components."""
        self._logger.info("Shutting down...")
        self._running = False

        self._safe_stop("Encerramento do processo")
        if self._camera:
            self._camera.stop()
        if self._serial:
            self._serial.close()
        if self._status_server:
            self._status_server.stop()

        total_time = time.time() - self._start_time
        avg_fps = self._frame_count / total_time if total_time > 0 else 0
        self._logger.info(f"Pipeline stopped: {self._frame_count} frames in {total_time:.1f}s = {avg_fps:.1f} FPS avg")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    raise KeyboardInterrupt()


def main():
    parser = argparse.ArgumentParser(description="EcoFlutuador POC - Autonomous Navigation")
    parser.add_argument("mode", choices=["mock", "dry-run", "real", "production", "camera-test", "uart-test", "sensor-test"],
                        help="Execution mode: mock (simulated), dry-run (camera+detect, no serial), real (full)")
    parser.add_argument("-c", "--config", default=str(Path(__file__).with_name("config.yaml")),
                        help="Path to config.yaml")
    parser.add_argument("--list-cameras", action="store_true",
                        help="List available cameras and exit")
    parser.add_argument("--log-level", default=None,
                        help="Override log level (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument("--simulate-start-after", type=float, default=None)
    parser.add_argument("--simulate-clear-after", type=float, default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--detector-backend", choices=["mock", "legacy_ssd"])
    parser.add_argument("--allow-control", action="store_true", help="Explicit hardware-control enable (production only)")
    args = parser.parse_args()
    if args.mode == "production":
        args.mode = "real"
    if args.mode == "real" and (args.simulate_start_after is not None or args.simulate_clear_after is not None):
        parser.error("START simulado permitido somente em mock/dry-run")

    # List cameras
    if args.list_cameras:
        print("Available cameras:")
        for idx in list_cameras():
            print(f"  {idx}")
        # Also list Picamera2 modes if available
        try:
            from picamera2 import Picamera2
            p = Picamera2()
            modes = p.sensor_modes
            print(f"\nPicamera2 sensor modes ({len(modes)} available):")
            for m in modes:
                size = m.get('size', (0, 0))
                fmt = m.get('format', 'N/A')
                fps = m.get('fps', 'N/A')
                print(f"  {size[0]}x{size[1]} @ {fps}fps ({fmt})")
            p.close()
        except ImportError:
            pass
        return 0

    # Load config
    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("Copy config.yaml.example to config.yaml and adjust paths.")
        return 1

    try:
        config = load_config(config_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    if args.detector_backend:
        config.setdefault("model", {})["backend"] = args.detector_backend
    if args.mode in {"camera-test", "uart-test", "sensor-test"}:
        from core.diagnostics import run_diagnostic
        return run_diagnostic(args.mode, config, args.duration or 5)
    if args.duration is not None and args.duration <= 0:
        parser.error("duration must be positive")
    if args.simulate_start_after is not None:
        config["simulation"] = {"start_after_s": args.simulate_start_after}
        if args.simulate_clear_after is not None:
            config["simulation"]["clear_after_s"] = args.simulate_clear_after
    if args.mode == "real":
        config.pop("simulation", None)
    config["duration_s"] = args.duration

    # Override log level if provided
    if args.log_level:
        config.setdefault("logging", {})["level"] = args.log_level

    setup_logging(config)

    # Safety check for real mode
    if args.mode == "real":
        print("\n⚠️  REAL MODE: Commands WILL be sent to ESP32 via serial.")
        print("Ensure ESP32 is connected and firmware is running.")
        confirm = "yes" if args.allow_control else input("Continue? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            print("Aborted.")
            return 0

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run pipeline
    pipeline = Pipeline(config, args.mode)
    if not pipeline.setup():
        return 1

    return pipeline.run()


if __name__ == "__main__":
    sys.exit(main())
