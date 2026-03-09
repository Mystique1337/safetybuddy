"""
SafetyBuddy — Flask Application Factory
"""
import os
import sys
from flask import Flask
from dotenv import load_dotenv

# Add project root to path (src/ui -> src -> safetybuddy)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def create_app(config_name=None):
    """Application factory pattern."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )

    # Config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "safetybuddy-dev-key-change-in-prod")
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit
    app.config["PROJECT_ROOT"] = PROJECT_ROOT

    # Register blueprints
    from src.ui.routes.pages import pages_bp
    from src.ui.routes.api import api_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
