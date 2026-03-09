"""
SafetyBuddy — Page routes (HTML views).
"""
from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    """Dashboard / landing page."""
    return render_template("dashboard.html")


@pages_bp.route("/chat")
def chat():
    """Chat page — RAG-powered PPE advisor."""
    return render_template("chat.html")


@pages_bp.route("/monitor")
def monitor():
    """Video monitor page — YOLO26 PPE detection."""
    return render_template("monitor.html")


@pages_bp.route("/compliance")
def compliance():
    """Compliance reference page."""
    return render_template("compliance.html")
