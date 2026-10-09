"""Small observability snapshots. No media, no control path, no network I/O."""
from datetime import datetime, timezone
from collections import deque
import time
from pathlib import Path

COMMANDS={"s":"STOP", "a":"LEFT", "w":"FORWARD", "d":"RIGHT"}


def snapshot(state, runtime, esp, device_id="eco-01"):
    esp=esp or {}
    water=esp.get("water", {})
    gps=esp.get("gps", {})
    command=runtime.get("decision_details", {}).get("current_command", state.get("decision", "s"))
    connected=runtime.get("serial_connected", False)
    return {
        "schema_version": 1, "device_id": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": {"state": runtime.get("operational_state", "WAITING"), "uptime_s": runtime.get("uptime_s",0),
                   "mode": runtime.get("mode"), "last_error": runtime.get("last_error")},
        "navigation": {"command": COMMANDS.get(command,"STOP")},
        "vision": {"detected": state.get("detected",False), "class": state.get("object"),
                   "confidence": state.get("confidence") if state.get("detected") else None,
                   "zone": state.get("zone") if state.get("detected") else None,
                   "model_version": runtime.get("model_version"), "backend": runtime.get("detector_backend")},
        "sensors": {"temperature_c": water.get("temperature_c"), "ph": water.get("ph"),
                    "turbidity_ntu": water.get("turbidity_ntu"), "distance_cm": esp.get("ultrasonic",{}).get("distance_cm")},
        "gps": {"lat": gps.get("lat"), "lon": gps.get("lon"), "fix": bool(connected and gps.get("valid",False))},
        "communication": {"esp32_connected": connected, "telemetry_age_ms": runtime.get("telemetry_age_ms"),
                          "firmware_version": esp.get("firmware_version"), "protocol_version": esp.get("protocol_version")},
    }


class EventHistory:
    def __init__(self, capacity=100, interval_s=5):
        self.events=deque(maxlen=capacity)
        self.interval_s=interval_s
        self._last_key=None
        self._last_time=-float("inf")

    def update(self, payload, now=None):
        now=time.monotonic() if now is None else now
        key=(payload["system"]["state"], payload["system"]["last_error"],
             payload["navigation"]["command"], payload["vision"]["class"], payload["vision"]["zone"],
             payload["communication"]["esp32_connected"])
        if key!=self._last_key or now-self._last_time>=self.interval_s:
            self.events.append(payload)
            self._last_key,self._last_time=key,now
            return True
        return False


class HostMetrics:
    """Process CPU over sample interval, current RSS on Linux, optional SoC temp."""
    def __init__(self):
        self._wall=time.monotonic()
        self._cpu=time.process_time()
        self.value={}

    def sample(self):
        now=time.monotonic()
        if self.value and now-self._wall<5:
            return self.value
        cpu=time.process_time()
        rss=None
        try:
            for line in Path('/proc/self/status').read_text().splitlines():
                if line.startswith('VmRSS:'): rss=int(line.split()[1])*1024
        except OSError:
            pass
        temperature=None
        try:
            model=Path('/proc/device-tree/model').read_text()
            if 'Raspberry Pi' in model:
                temperature=int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000
        except (OSError,ValueError):
            pass
        self.value={"process_cpu_percent": round(100*(cpu-self._cpu)/max(now-self._wall,.001),2),
                    "rss_bytes": rss, "temperature_c": temperature}
        self._cpu,self._wall=cpu,now
        return self.value
