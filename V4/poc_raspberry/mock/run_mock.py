#!/usr/bin/env python3
"""
Mock runner for EcoFlutuador POC.
Runs the full pipeline with simulated camera and serial.
Use for testing logic on notebook without hardware.
"""
import sys
import os
import argparse
import time
import logging
import signal
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.camera import CameraConfig
from core.detector import ModelConfig
from core.decision import DecisionConfig
from core.serial_link import SerialConfig
from core.state import DetectionState
from mock.camera_mock import MockCamera, MockCameraConfig
from mock.serial_mock import MockSerialLink, MockSerialConfig


def setup_logging(level: str = "INFO", json_format: bool = True):
    """Configure logging."""
    from core.logging_config import setup_logging as configure
    configure({"logging": {"level": level}})


def run_mock(num_frames: int = 100, target_fps: int = 10, width: int = 320, height: int = 240, verbose: bool = True):
    """
    Run mock pipeline.
    Returns True if successful.
    """
    from main import Pipeline
    from core.decision import DecisionEngine
    import numpy as np
    import cv2
    pipeline = Pipeline({"recognition": {"confirmation_s": 0}}, "mock")
    pipeline._decision = DecisionEngine(DecisionConfig(confirmation_frames=3, loss_timeout_s=.5, hysteresis_fraction=.04))
    pipeline._serial = MockSerialLink(MockSerialConfig(), on_response=pipeline._on_serial_response)
    pipeline._serial.start()
    commands = set()
    states = set()
    for index in range(num_frames):
        if index == 2:
            pipeline._on_serial_response("EVENT:START:1")
        if index == num_frames-2:
            pipeline._on_serial_response("EVENT:START:0")
        frame = np.zeros((height,width,3), dtype=np.uint8)
        fraction = (.15,.5,.85)[min(2, index*3//max(1,num_frames-2))]
        cx = int(width*fraction)
        cv2.rectangle(frame, (cx-20,height//2-30), (cx+20,height//2+30), (0,200,0), -1)
        pipeline._frame_count += 1
        state = pipeline._process_frame(frame)
        commands.add(state.decision)
        states.add(pipeline.controller.state.value)
        if verbose:
            print(json.dumps({**state.to_json(), **pipeline.runtime_status()}))
        time.sleep(1/target_fps)
    transmitted=set(pipeline._serial.sent_commands)
    pipeline.shutdown()
    success = {'s','a','w','d'} <= transmitted and {'s','a','w','d'} <= commands and {'WAITING','TRACKING'} <= states
    logging.getLogger("mock_runner").info("V4 mock: commands=%s states=%s success=%s", sorted(commands), sorted(states), success)
    return success


def main():
    parser = argparse.ArgumentParser(description="EcoFlutuador POC Mock Runner")
    parser.add_argument("--frames", type=int, default=100, help="Number of frames to process")
    parser.add_argument("--fps", type=int, default=10, help="Target FPS")
    parser.add_argument("--width", type=int, default=320, help="Mock frame width")
    parser.add_argument("--height", type=int, default=240, help="Mock frame height")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--no-json", action="store_true", help="Disable JSON logging")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-frame JSON output")
    args = parser.parse_args()

    setup_logging(args.log_level, json_format=not args.no_json)

    success = run_mock(
        num_frames=args.frames,
        target_fps=args.fps,
        width=args.width,
        height=args.height,
        verbose=not args.quiet
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()