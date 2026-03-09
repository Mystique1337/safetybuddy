"""
Real-time PPE detection using YOLO26.

YOLO26 advantages over YOLOv8:
- NMS-free end-to-end inference (no post-processing bottleneck)
- Up to 43% faster CPU inference
- Better small-object detection (ProgLoss + STAL)
- MuSGD optimizer for more stable training
"""
import cv2
import numpy as np
import time
import base64
from dataclasses import dataclass, field
from typing import Optional

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


PPE_CLASSES = {
    0: "Hardhat", 1: "Mask", 2: "NO-Hardhat", 3: "NO-Mask",
    4: "NO-Safety Vest", 5: "Person", 6: "Safety Cone",
    7: "Safety Vest", 8: "machinery", 9: "vehicle",
}

VIOLATION_CLASSES = {2, 3, 4}   # NO-Hardhat, NO-Mask, NO-Safety Vest
COMPLIANT_CLASSES = {0, 1, 7}   # Hardhat, Mask, Safety Vest

CLASS_COLORS = {
    0: (0, 255, 0),   1: (0, 255, 0),   2: (0, 0, 255),
    3: (0, 0, 255),   4: (0, 0, 255),   5: (255, 200, 0),
    6: (0, 255, 255), 7: (0, 255, 0),   8: (128, 128, 128),
    9: (128, 128, 128),
}


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    is_violation: bool


@dataclass
class FrameAnalysis:
    detections: list = field(default_factory=list)
    violation_count: int = 0
    compliant_count: int = 0
    has_violations: bool = False
    annotated_frame: Optional[np.ndarray] = None
    timestamp: float = 0.0


class PPEVideoDetector:
    """
    Real-time PPE detector using YOLO26 nano model.
    Runs on CPU at ~25-40 FPS, on GPU at ~80-120 FPS.
    """

    def __init__(self, model_path: str = "data/models/ppe_yolo26n.pt",
                 confidence_threshold: float = 0.4):
        if YOLO is None:
            raise ImportError("ultralytics not installed. Run: pip install ultralytics>=8.4.0")
        self.model = YOLO(model_path)
        self.conf_threshold = confidence_threshold
        self.last_alert_time = 0
        self.alert_cooldown_seconds = 30
        self.total_frames_processed = 0
        self.total_violations_detected = 0

    def detect_frame(self, frame: np.ndarray) -> FrameAnalysis:
        """Run PPE detection on a single video frame."""
        self.total_frames_processed += 1
        analysis = FrameAnalysis(timestamp=time.time())

        # YOLO26: NMS-free end-to-end inference
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            verbose=False,
        )

        if not results or len(results[0].boxes) == 0:
            analysis.annotated_frame = frame.copy()
            return analysis

        result = results[0]
        annotated = frame.copy()

        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            is_violation = cls_id in VIOLATION_CLASSES
            cls_name = PPE_CLASSES.get(cls_id, f"class_{cls_id}")

            analysis.detections.append(Detection(
                class_id=cls_id, class_name=cls_name,
                confidence=conf, bbox=(x1, y1, x2, y2),
                is_violation=is_violation))

            if is_violation:
                analysis.violation_count += 1
            elif cls_id in COMPLIANT_CLASSES:
                analysis.compliant_count += 1

            # Draw bounding box
            color = CLASS_COLORS.get(cls_id, (128, 128, 128))
            thickness = 3 if is_violation else 2
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)

            label = f"{cls_name} {conf:.0%}"
            lbl_sz = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(annotated, (x1, y1 - lbl_sz[1] - 10),
                         (x1 + lbl_sz[0] + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Status bar at top
        analysis.has_violations = analysis.violation_count > 0
        bar_color = (0, 0, 200) if analysis.has_violations else (0, 150, 0)
        status = (f"VIOLATIONS: {analysis.violation_count}"
                  if analysis.has_violations else "ALL CLEAR")
        cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 40), bar_color, -1)
        cv2.putText(annotated, f"YOLO26 PPE Monitor | {status}", (10, 28),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if analysis.has_violations:
            self.total_violations_detected += 1

        analysis.annotated_frame = annotated
        return analysis

    def should_trigger_alert(self) -> bool:
        """Check if enough time has passed to send another GPT-4o alert."""
        return (time.time() - self.last_alert_time) > self.alert_cooldown_seconds

    def mark_alert_sent(self):
        self.last_alert_time = time.time()

    def frame_to_base64(self, frame: np.ndarray) -> str:
        """Encode a frame as base64 JPEG for GPT-4o."""
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf).decode()

    def format_detections_for_llm(self, analysis: FrameAnalysis) -> str:
        """Format YOLO detections as text for GPT-4o prompt."""
        lines = []
        for d in analysis.detections:
            status = "VIOLATION" if d.is_violation else "COMPLIANT"
            lines.append(f"- [{status}] {d.class_name} (confidence: {d.confidence:.0%})")
        return "\n".join(lines) or "No PPE items detected in frame."

    def get_stats(self) -> dict:
        return {
            "total_frames": self.total_frames_processed,
            "total_violation_frames": self.total_violations_detected,
            "violation_rate": round(
                self.total_violations_detected / max(1, self.total_frames_processed) * 100, 1),
        }
