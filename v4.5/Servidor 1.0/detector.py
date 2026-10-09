"""Detecção e anotação de garrafas; não conhece motores, serial ou Flask."""
import cv2


class Detector:
    def __init__(self, model_dir):
        with (model_dir / "coco.names").open(encoding="utf-8") as stream:
            self._classes = stream.read().splitlines()
        self._net = cv2.dnn_DetectionModel(
            str(model_dir / "frozen_inference_graph.pb"),
            str(model_dir / "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt"),
        )
        self._net.setInputSize(320, 320)
        self._net.setInputScale(1.0 / 127.5)
        self._net.setInputMean((127.5, 127.5, 127.5))
        self._net.setInputSwapRB(True)

    def detect(self, frame, threshold=0.45, nms=0.2):
        ids, confidences, boxes = self._net.detect(
            frame, confThreshold=threshold, nmsThreshold=nms)
        objects = []
        if len(ids):
            for class_id, confidence, box in zip(ids.flatten(), confidences.flatten(), boxes):
                name = self._classes[int(class_id) - 1]
                if name != "bottle":
                    continue
                box = [int(value) for value in box]
                objects.append([box, name])
                cv2.rectangle(frame, box, color=(0, 255, 0), thickness=2)
                cv2.putText(frame, name.upper(), (box[0] + 10, box[1] + 30),
                            cv2.FONT_HERSHEY_COMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(frame, f"{float(confidence) * 100:.1f}%", (box[0] + 10, box[1] + 58),
                            cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 200, 0), 1)
        return frame, objects
