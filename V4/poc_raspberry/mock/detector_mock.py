"""Explicit synthetic green-object backend; never a substitute for failed weights."""
import cv2
import numpy as np
from core.contracts import Detection


class MockDetector:
    def detect(self, frame):
        hsv=cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv, np.array([35,50,50]), np.array([85,255,255]))
        contours,_=cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [Detection(list(cv2.boundingRect(c)), "bottle", .9)
                for c in contours if cv2.contourArea(c)>500]
