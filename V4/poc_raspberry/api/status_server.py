"""
Minimal HTTP status API for EcoFlutuador POC.
Provides GET /status endpoint returning current detection state as JSON.
Optional - can be disabled in config.
"""
from flask import Flask, jsonify, render_template
from core.telemetry import snapshot, EventHistory, HostMetrics
from werkzeug.serving import make_server
from copy import deepcopy
import threading
import time
import logging
from typing import Optional, Dict, Any
from core.state import DetectionState


class StatusServer:
    """
    Simple Flask server for status API.
    Runs in daemon thread, non-blocking.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080, device_id="eco-01", telemetry_timeout_s=3):
        self.telemetry_timeout_s=telemetry_timeout_s
        self.device_id=device_id
        self._history=EventHistory()
        self._metrics=HostMetrics()
        self.host = host
        self.port = port
        self._app = Flask(__name__)
        self._state: Optional[DetectionState] = DetectionState.empty()
        self._runtime = {}
        self._telemetry_time = None
        self._server = None
        self._telemetry: Optional[Dict[str, Any]] = None
        self._state_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(__name__)
        self._setup_routes()

    def _snapshot(self):
        runtime=dict(self._runtime)
        if self._telemetry_time is not None:
            runtime["telemetry_age_ms"]=max(0,int((time.monotonic()-self._telemetry_time)*1000))
            if runtime["telemetry_age_ms"]>self.telemetry_timeout_s*1000:
                runtime["serial_connected"]=False
        return snapshot(self._state.to_json(), runtime, self._telemetry, self.device_id)

    def _setup_routes(self) -> None:
        @self._app.route("/")
        def dashboard():
            return render_template("dashboard.html")

        @self._app.route("/telemetry")
        def telemetry():
            with self._state_lock:
                return jsonify(self._snapshot())

        @self._app.route("/history")
        def history():
            with self._state_lock:
                return jsonify(list(self._history.events))

        @self._app.route("/diagnostics")
        def diagnostics():
            with self._state_lock:
                return jsonify({"host": self._metrics.sample(), "runtime": self._runtime,
                                "history_count": len(self._history.events)})
        @self._app.route("/status", methods=["GET"])
        def status():
            with self._state_lock:
                if self._state is None:
                    return jsonify({"error": "No state available yet"}), 503
                payload = self._state.to_json()
                payload["decision"] = self._runtime.get("decision_details", {}).get("current_command", payload["decision"])
                payload["telemetry"] = self._telemetry
                payload.update(self._runtime)
                payload.setdefault("operational_state", "WAITING")
                payload.setdefault("recognition_active", False)
                payload.setdefault("serial_connected", False)
                payload.setdefault("camera_backend", None)
                payload.setdefault("last_error", None)
                tel = self._telemetry or {}
                payload.setdefault("ultrasonic", tel.get("ultrasonic", {}))
                payload.setdefault("net", tel.get("net", {}))
                payload["environmental"] = tel.get("water", {})
                payload["telemetry_age_ms"] = (None if self._telemetry_time is None else
                    max(0, int((time.monotonic()-self._telemetry_time)*1000)))
                if payload["telemetry_age_ms"] is not None and payload["telemetry_age_ms"] > self.telemetry_timeout_s*1000:
                    payload["serial_connected"] = False
                return jsonify(payload)

        @self._app.route("/detections", methods=["GET"])
        def detections():
            with self._state_lock:
                return jsonify(self._state.to_json())

        @self._app.route("/decision", methods=["GET"])
        def decision():
            with self._state_lock:
                return jsonify({"decision": self._runtime.get("decision_details", {}).get("current_command", self._state.decision),
                                **self._runtime.get("decision_details", {})})

        @self._app.route("/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok", "timestamp": time.time()})

    def update_state(self, state: DetectionState) -> None:
        """Update current state (called from main loop)."""
        with self._state_lock:
            self._state = state

    def update_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """Update the latest validated ESP32 telemetry payload."""
        with self._state_lock:
            self._telemetry = deepcopy(telemetry)
            self._telemetry_time = time.monotonic()

    def update_runtime(self, runtime):
        with self._state_lock:
            self._runtime = deepcopy(runtime)
            self._history.update(self._snapshot())

    def start(self) -> None:
        """Start server in daemon thread."""
        if self._thread is not None:
            return

        self._server = make_server(self.host, self.port, self._app, threaded=True)
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="StatusServer"
        )
        self._thread.start()
        self._logger.info(f"Status API started on http://{self.host}:{self.port}/status")

    def _run(self) -> None:
        """Run Flask app (blocking)."""
        # Disable Flask's default logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.WARNING)
        self._server.serve_forever()

    def stop(self) -> None:
        """Release the HTTP socket and join the serving thread."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=2)
            self._thread = None
            self._server = None
        self._logger.info("Status API stopping")
