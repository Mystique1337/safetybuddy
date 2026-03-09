"""
SafetyBuddy — REST API routes.
Handles chat, image analysis, video processing, and dashboard data.
"""
import os
import io
import base64
import uuid
import time
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

api_bp = Blueprint("api", __name__)

# In-memory session store (replace with Redis/DB for production)
_session_store = {
    "messages": [],
    "alerts": [],
    "stats": {"queries": 0, "images_analyzed": 0, "video_frames": 0, "violations": 0},
}


def _get_store():
    return _session_store


# ── Chat Endpoint ──────────────────────────────────────────

@api_bp.route("/chat", methods=["POST"])
def chat():
    """Process a chat message through the RAG pipeline."""
    from src.rag.chains import query_safetybuddy
    from src.compliance.mapper import enrich_with_compliance

    data = request.get_json()
    user_query = data.get("message", "").strip()
    mode = data.get("mode", "advisor")
    doc_filter = data.get("doc_filter", None)
    n_results = data.get("n_results", 5)
    image_b64 = data.get("image_base64", None)
    image_desc = data.get("image_description", None)

    if not user_query:
        return jsonify({"error": "Message is required"}), 400

    store = _get_store()
    store["stats"]["queries"] += 1

    try:
        result = query_safetybuddy(
            user_query,
            mode=mode,
            doc_type_filter=doc_filter if doc_filter != "all" else None,
            n_results=n_results,
            image_base64=image_b64,
            image_description=image_desc,
        )
        compliance = enrich_with_compliance(user_query, result["response"], image_desc)

        # Store message
        msg = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "user_query": user_query,
            "response": result["response"],
            "sources": result["sources"],
            "compliance": compliance["compliance_summary"],
            "traceability": compliance["traceability_note"],
            "mode": mode,
            "tokens_used": result["tokens_used"],
        }
        store["messages"].append(msg)

        return jsonify(msg)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Image Analysis Endpoint ────────────────────────────────

@api_bp.route("/analyze-image", methods=["POST"])
def analyze_image_endpoint():
    """Analyze an uploaded image for PPE compliance (GPT-4o + optional YOLO annotations)."""
    from src.vision.image_analyzer import analyze_image

    store = _get_store()
    img_b64 = None

    try:
        if "image" in request.files:
            file = request.files["image"]
            img_bytes = file.read()
            if not img_bytes:
                return jsonify({"error": "Empty image file"}), 400
            img_b64 = base64.b64encode(img_bytes).decode()
        elif request.is_json and request.json.get("image_base64"):
            img_b64 = request.json["image_base64"]
        else:
            return jsonify({"error": "No image provided. Upload a file or send base64."}), 400

        context = ""
        if request.form:
            context = request.form.get("context", "")

        # --- GPT-4o vision analysis ---
        result = analyze_image(img_b64, additional_context=context, is_base64=True)
        store["stats"]["images_analyzed"] += 1

        # --- YOLO26 annotation pass (if model available) ---
        annotated_b64 = None
        yolo_detections = []
        try:
            detector = _get_live_detector()
            if detector is not None:
                import cv2
                import numpy as np
                raw_bytes = base64.b64decode(img_b64)
                nparr = np.frombuffer(raw_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None:
                    analysis = detector.detect_frame(frame)
                    _, buf = cv2.imencode(".jpg", analysis.annotated_frame,
                                          [cv2.IMWRITE_JPEG_QUALITY, 90])
                    annotated_b64 = base64.b64encode(buf).decode()
                    yolo_detections = [
                        {
                            "class_name": d.class_name,
                            "confidence": round(d.confidence, 2),
                            "is_violation": d.is_violation,
                        }
                        for d in analysis.detections
                    ]
        except Exception:
            pass  # YOLO is optional — GPT-4o analysis still returns

        return jsonify({
            "analysis": result["analysis"],
            "tokens_used": result["tokens_used"],
            "timestamp": datetime.now().isoformat(),
            "annotated_image": annotated_b64,
            "yolo_detections": yolo_detections,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Image analysis failed: {str(e)}"}), 500


# ── Video Upload & Process Endpoint ────────────────────────

@api_bp.route("/process-video", methods=["POST"])
def process_video():
    """Process an uploaded video for PPE violations frame-by-frame."""
    import cv2
    import numpy as np

    store = _get_store()
    project_root = current_app.config["PROJECT_ROOT"]
    model_path = os.path.join(project_root, "data", "models", "ppe_yolo26n.pt")

    if not os.path.exists(model_path):
        return jsonify({"error": "YOLO model not found. Train and place ppe_yolo26n.pt in data/models/"}), 404

    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    from src.vision.video_detector import PPEVideoDetector

    file = request.files["video"]
    conf = float(request.form.get("confidence", 0.4))

    # Save temp file
    temp_path = os.path.join(project_root, "data", f"temp_{uuid.uuid4().hex}.mp4")
    file.save(temp_path)

    try:
        detector = PPEVideoDetector(model_path=model_path, confidence_threshold=conf)
        cap = cv2.VideoCapture(temp_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_skip = max(1, int(fps / 5))

        violations = []
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if frame_idx % frame_skip != 0:
                continue

            analysis = detector.detect_frame(frame)
            store["stats"]["video_frames"] += 1

            if analysis.has_violations:
                vnames = [d.class_name for d in analysis.detections if d.is_violation]
                violations.append({
                    "frame": frame_idx,
                    "time_sec": round(frame_idx / fps, 1),
                    "violations": vnames,
                    "thumbnail": detector.frame_to_base64(analysis.annotated_frame),
                })
                store["stats"]["violations"] += 1
                store["alerts"].append({
                    "id": str(uuid.uuid4()),
                    "time": f"{frame_idx / fps:.1f}s",
                    "summary": ", ".join(vnames),
                    "severity": "HIGH",
                    "timestamp": datetime.now().isoformat(),
                    "source": "video",
                })

        cap.release()

        return jsonify({
            "total_frames": total_frames,
            "processed_frames": detector.total_frames_processed,
            "violations": violations[:20],  # limit response size
            "violation_count": len(violations),
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ── Live Frame Detection (Webcam) ──────────────────────────

# Cache the detector so we don't reload the model every frame
_live_detector = None


def _get_live_detector():
    global _live_detector
    if _live_detector is None:
        model_path = os.path.join(
            current_app.config["PROJECT_ROOT"], "data", "models", "ppe_yolo26n.pt"
        )
        if not os.path.exists(model_path):
            return None
        from src.vision.video_detector import PPEVideoDetector
        _live_detector = PPEVideoDetector(model_path=model_path, confidence_threshold=0.4)
    return _live_detector


@api_bp.route("/detect-frame", methods=["POST"])
def detect_frame():
    """
    Receive a single webcam frame (base64 JPEG), run YOLO26,
    return the annotated frame + detection results.
    """
    import cv2
    import numpy as np

    data = request.get_json()
    frame_b64 = data.get("frame")
    conf = data.get("confidence", 0.4)

    if not frame_b64:
        return jsonify({"error": "No frame data"}), 400

    detector = _get_live_detector()
    if detector is None:
        return jsonify({"error": "YOLO model not found at data/models/ppe_yolo26n.pt"}), 404

    detector.conf_threshold = conf
    store = _get_store()

    try:
        # Decode base64 JPEG → numpy array
        img_bytes = base64.b64decode(frame_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"error": "Could not decode frame"}), 400

        # Run YOLO26
        analysis = detector.detect_frame(frame)
        store["stats"]["video_frames"] += 1

        # Encode annotated frame back to base64 JPEG
        _, buf = cv2.imencode(".jpg", analysis.annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        annotated_b64 = base64.b64encode(buf).decode()

        # Build detections list
        detections = []
        for d in analysis.detections:
            detections.append({
                "class_name": d.class_name,
                "confidence": round(d.confidence, 2),
                "is_violation": d.is_violation,
                "bbox": d.bbox,
            })

        # Log violations
        if analysis.has_violations:
            store["stats"]["violations"] += 1
            vnames = [d.class_name for d in analysis.detections if d.is_violation]
            store["alerts"].append({
                "id": str(uuid.uuid4()),
                "time": datetime.now().strftime("%H:%M:%S"),
                "summary": ", ".join(vnames),
                "severity": "HIGH",
                "timestamp": datetime.now().isoformat(),
                "source": "live",
            })

        return jsonify({
            "annotated_frame": annotated_b64,
            "has_violations": analysis.has_violations,
            "violation_count": analysis.violation_count,
            "compliant_count": analysis.compliant_count,
            "detections": detections,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_bp.route("/model-status", methods=["GET"])
def model_status():
    """Check if YOLO model is available for live detection."""
    model_path = os.path.join(
        current_app.config["PROJECT_ROOT"], "data", "models", "ppe_yolo26n.pt"
    )
    return jsonify({"available": os.path.exists(model_path)})


# ── GPT-4o Deep Analysis of Video Violation ────────────────

@api_bp.route("/analyze-violation", methods=["POST"])
def analyze_violation():
    """Run GPT-4o deep analysis on a specific video violation frame."""
    from src.rag.chains import query_safetybuddy
    from src.compliance.mapper import enrich_with_compliance

    data = request.get_json()
    detections_text = data.get("detections", "")
    image_b64 = data.get("image_base64", None)

    if not detections_text:
        return jsonify({"error": "Detections text required"}), 400

    try:
        result = query_safetybuddy(
            f"PPE violations detected: {detections_text}",
            mode="video_alert",
            detections=detections_text,
            image_base64=image_b64,
            n_results=3,
        )
        compliance = enrich_with_compliance(detections_text, result["response"])

        return jsonify({
            "analysis": result["response"],
            "compliance": compliance["compliance_summary"],
            "traceability": compliance["traceability_note"],
            "sources": result["sources"],
            "tokens_used": result["tokens_used"],
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Dashboard Data ─────────────────────────────────────────

@api_bp.route("/dashboard", methods=["GET"])
def dashboard_data():
    """Return dashboard stats and recent alerts."""
    store = _get_store()
    return jsonify({
        "stats": store["stats"],
        "alerts": store["alerts"][-50:],
        "recent_messages": [
            {
                "id": m["id"],
                "timestamp": m["timestamp"],
                "query": m["user_query"][:100],
                "mode": m["mode"],
            }
            for m in store["messages"][-20:]
        ],
    })


@api_bp.route("/alerts", methods=["GET"])
def get_alerts():
    """Return all alerts."""
    store = _get_store()
    return jsonify({"alerts": store["alerts"]})


# ── Health Check ───────────────────────────────────────────

@api_bp.route("/health", methods=["GET"])
def health():
    """Health check for load balancers / container orchestration."""
    model_path = os.path.join(current_app.config["PROJECT_ROOT"], "data", "models", "ppe_yolo26n.pt")
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "yolo_model_available": os.path.exists(model_path),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
    })
