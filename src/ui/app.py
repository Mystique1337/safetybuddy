"""
SafetyBuddy — Main Streamlit Application
Run: streamlit run src/ui/app.py
"""
import streamlit as st
import sys
import os
import base64
import io
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

st.set_page_config(page_title="SafetyBuddy", page_icon="🛡️", layout="wide")

# ── Initialize session state ──
if "messages" not in st.session_state:
    st.session_state.messages = []
if "video_alerts" not in st.session_state:
    st.session_state.video_alerts = []

# ── Sidebar ──
st.sidebar.title("🛡️ SafetyBuddy")
st.sidebar.caption("PPE Compliance Intelligence Platform")
st.sidebar.divider()
page = st.sidebar.radio("Navigate", ["💬 Chat", "📹 Video Monitor", "📊 Dashboard"])

# ═══════════════════════════════════════════════════════════
# PAGE 1: CHAT
# ═══════════════════════════════════════════════════════════
if page == "💬 Chat":
    from src.rag.chains import query_safetybuddy
    from src.vision.image_analyzer import analyze_image
    from src.compliance.mapper import enrich_with_compliance

    st.header("💬 SafetyBuddy Chat")

    mode = st.sidebar.selectbox("Analysis Mode",
        ["Safety Advisor", "Incident Analyst", "Compliance Auditor"])
    mode_map = {"Safety Advisor": "advisor", "Incident Analyst": "incident",
                "Compliance Auditor": "compliance"}
    doc_filter = st.sidebar.selectbox("Filter Sources",
        [None, "regulation", "operating_procedure", "incident_report", "safety_manual"],
        format_func=lambda x: "All Documents" if x is None else x.replace("_", " ").title())
    n_results = st.sidebar.slider("Sources to retrieve", 3, 10, 5)

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sources" in msg:
                with st.expander("📄 Sources"):
                    for s in msg["sources"]:
                        st.markdown(f"- **{s['source']}** (p.{s['page']}) | {s['type']}")
            if "compliance" in msg:
                with st.expander("📋 Regulations"):
                    st.markdown(msg["compliance"])

    # Image upload
    uploaded = st.file_uploader("Upload inspection image (optional)", type=["jpg", "jpeg", "png"])
    img_b64 = None
    img_analysis = None

    if uploaded:
        from PIL import Image
        img = Image.open(uploaded)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(img, caption="Uploaded image", use_container_width=True)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()
        with c2:
            if st.button("🔍 Analyze Image for PPE"):
                with st.spinner("Analyzing with GPT-4o Vision..."):
                    r = analyze_image(img_b64, is_base64=True)
                    img_analysis = r["analysis"]
                    st.markdown(img_analysis)
                    st.caption(f"Tokens used: {r['tokens_used']}")

    # Chat input
    if prompt := st.chat_input("Describe a PPE situation or ask a question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing..."):
                result = query_safetybuddy(
                    prompt, mode=mode_map[mode], doc_type_filter=doc_filter,
                    n_results=n_results, image_base64=img_b64,
                    image_description=img_analysis)
                compliance = enrich_with_compliance(prompt, result["response"], img_analysis)

                st.markdown(result["response"])
                with st.expander("📄 Sources & Traceability"):
                    for s in result["sources"]:
                        st.markdown(
                            f"- **{s['source']}** (p.{s['page']}) | "
                            f"{s['type']} | relevance: {s['relevance']}")
                with st.expander("📋 Regulatory Compliance"):
                    st.markdown(compliance["compliance_summary"])
                    st.caption(compliance["traceability_note"])
                st.caption(f"Mode: {mode} | Tokens: {result['tokens_used']}")

            st.session_state.messages.append({
                "role": "assistant", "content": result["response"],
                "sources": result["sources"],
                "compliance": compliance["compliance_summary"],
            })


# ═══════════════════════════════════════════════════════════
# PAGE 2: VIDEO MONITOR
# ═══════════════════════════════════════════════════════════
elif page == "📹 Video Monitor":
    import cv2
    import numpy as np

    st.header("📹 Real-Time PPE Monitor")

    MODEL_PATH = os.path.join(PROJECT_ROOT, "data", "models", "ppe_yolo26n.pt")

    if not os.path.exists(MODEL_PATH):
        st.error(f"⚠️ YOLO26 model not found at `{MODEL_PATH}`")
        st.markdown("""
        **To set up the video monitor:**
        1. Train YOLO26 using the provided Colab notebook (`notebooks/train_yolo_ppe.ipynb`)
        2. Download the `best.pt` file from training
        3. Save it as `data/models/ppe_yolo26n.pt`

        **You can still use the Chat page** for text + image analysis while the model trains.
        """)
        st.stop()

    from src.vision.video_detector import PPEVideoDetector
    from src.rag.chains import query_safetybuddy
    from src.compliance.mapper import enrich_with_compliance

    @st.cache_resource
    def load_detector():
        return PPEVideoDetector(model_path=MODEL_PATH, confidence_threshold=0.4)

    detector = load_detector()

    # Sidebar controls
    st.sidebar.subheader("Monitor Settings")
    conf = st.sidebar.slider("Detection Confidence", 0.2, 0.9, 0.4, 0.05)
    detector.conf_threshold = conf
    cooldown = st.sidebar.slider("Alert Cooldown (sec)", 10, 120, 30, 5)
    detector.alert_cooldown_seconds = cooldown
    auto_analyze = st.sidebar.checkbox("Auto-analyze with GPT-4o", value=True)

    col_feed, col_alerts = st.columns([2, 1])

    with col_alerts:
        st.subheader("🚨 Alert Log")
        for alert in reversed(st.session_state.video_alerts[-15:]):
            sev = alert.get("severity", "MEDIUM")
            icon = "🔴" if sev == "HIGH" else "🟡"
            st.markdown(f"{icon} **{alert['time']}** — {alert['summary']}")
            if alert.get("analysis"):
                with st.expander("GPT-4o Details"):
                    st.markdown(alert["analysis"])

    with col_feed:
        feed_mode = st.radio("Feed Source",
            ["📷 Webcam (Live)", "📁 Upload Video File"], horizontal=True)

        if feed_mode == "📷 Webcam (Live)":
            try:
                from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
                import av

                RTC_CONFIG = RTCConfiguration(
                    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

                def video_callback(frame):
                    img = frame.to_ndarray(format="bgr24")
                    analysis = detector.detect_frame(img)
                    return av.VideoFrame.from_ndarray(analysis.annotated_frame, format="bgr24")

                webrtc_streamer(
                    key="ppe-monitor",
                    mode=WebRtcMode.SENDRECV,
                    rtc_configuration=RTC_CONFIG,
                    video_frame_callback=video_callback,
                    media_stream_constraints={"video": True, "audio": False},
                    async_processing=True,
                )
                st.caption("Click START for live PPE monitoring. Green = OK, Red = Violation.")

            except ImportError:
                st.warning(
                    "Install `streamlit-webrtc` for live webcam support:\n"
                    "```pip install streamlit-webrtc```\n\n"
                    "Use 'Upload Video File' mode in the meantime.")

        else:
            # Upload video file mode
            video_file = st.file_uploader("Upload a video", type=["mp4", "avi", "mov"])

            if video_file:
                temp_path = os.path.join(PROJECT_ROOT, "data", "temp_video.mp4")
                with open(temp_path, "wb") as f:
                    f.write(video_file.read())

                if st.button("▶️ Start PPE Analysis", type="primary"):
                    cap = cv2.VideoCapture(temp_path)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 30
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    frame_skip = max(1, int(fps / 5))  # ~5 FPS processing

                    progress = st.progress(0, text="Processing video...")
                    frame_display = st.empty()
                    stats_display = st.empty()

                    frame_idx = 0
                    violation_frames = []

                    while cap.isOpened():
                        ret, frame = cap.read()
                        if not ret:
                            break
                        frame_idx += 1
                        if frame_idx % frame_skip != 0:
                            continue

                        analysis = detector.detect_frame(frame)
                        rgb = cv2.cvtColor(analysis.annotated_frame, cv2.COLOR_BGR2RGB)
                        frame_display.image(rgb, channels="RGB", use_container_width=True)

                        if analysis.has_violations:
                            vnames = [d.class_name for d in analysis.detections if d.is_violation]
                            violation_frames.append({
                                "frame": frame_idx,
                                "time_sec": round(frame_idx / fps, 1),
                                "violations": vnames,
                                "frame_b64": detector.frame_to_base64(frame),
                                "detections_text": detector.format_detections_for_llm(analysis),
                            })
                            st.session_state.video_alerts.append({
                                "time": f"{frame_idx / fps:.1f}s",
                                "summary": f"{', '.join(vnames)}",
                                "severity": "HIGH",
                            })

                        pct = min(frame_idx / max(1, total_frames), 1.0)
                        progress.progress(pct, f"Frame {frame_idx}/{total_frames}")
                        stats = detector.get_stats()
                        stats_display.markdown(
                            f"**Processed:** {stats['total_frames']} | "
                            f"**Violations:** {stats['total_violation_frames']} | "
                            f"**Rate:** {stats['violation_rate']}%")

                    cap.release()
                    progress.progress(1.0, "✅ Complete!")

                    # GPT-4o analysis of worst violations
                    if violation_frames and auto_analyze:
                        st.subheader("🤖 GPT-4o Deep Analysis")
                        for i, vf in enumerate(violation_frames[:3]):
                            with st.spinner(f"Analyzing violation {i + 1}..."):
                                result = query_safetybuddy(
                                    f"PPE violations: {vf['detections_text']}",
                                    mode="video_alert",
                                    detections=vf["detections_text"],
                                    image_base64=vf["frame_b64"],
                                    n_results=3)
                                comp = enrich_with_compliance(
                                    vf["detections_text"], result["response"])
                                st.markdown(f"**@ {vf['time_sec']}s:**")
                                st.markdown(result["response"])
                                with st.expander("📋 Regulations"):
                                    st.markdown(comp["compliance_summary"])
                                st.divider()
                    elif not violation_frames:
                        st.success("✅ No PPE violations detected!")

                    # Cleanup
                    if os.path.exists(temp_path):
                        os.remove(temp_path)


# ═══════════════════════════════════════════════════════════
# PAGE 3: DASHBOARD
# ═══════════════════════════════════════════════════════════
elif page == "📊 Dashboard":
    st.header("📊 PPE Compliance Dashboard")

    alerts = st.session_state.get("video_alerts", [])
    messages = st.session_state.get("messages", [])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Alerts", len(alerts))
    with c2:
        high = sum(1 for a in alerts if a.get("severity") == "HIGH")
        st.metric("High Severity", high)
    with c3:
        queries = len([m for m in messages if m.get("role") == "user"])
        st.metric("Chat Queries", queries)
    with c4:
        st.metric("Session", datetime.now().strftime("%H:%M"))

    st.divider()
    st.subheader("Recent Alerts")
    if alerts:
        for alert in reversed(alerts[-20:]):
            c1, c2, c3 = st.columns([1, 3, 1])
            with c1:
                st.write(alert.get("time", ""))
            with c2:
                st.write(alert.get("summary", ""))
            with c3:
                sev = alert.get("severity", "LOW")
                colors = {"HIGH": "red", "MEDIUM": "orange", "LOW": "green"}
                st.markdown(f":{colors.get(sev, 'gray')}[{sev}]")
    else:
        st.info("No alerts yet. Start the Video Monitor to begin detecting PPE violations.")

    st.divider()
    st.subheader("PPE Compliance Quick Reference")
    st.markdown("""
| PPE Type | OSHA Standard | Required When |
|----------|--------------|---------------|
| Hard Hat | 1910.135 | Falling/flying object risk |
| Safety Glasses | 1910.133 | Impact, splash, vapor risk |
| Gloves | 1910.138 | Chemical, cut, heat exposure |
| Safety Boots | 1910.136 | Falling/rolling objects, piercing |
| Respirator | 1910.134 | Airborne contaminant exposure |
| Hearing Protection | 1910.95 | Noise > 85 dBA TWA |
| High-Vis Vest | 1910.132 | Vehicle/equipment traffic areas |
""")
