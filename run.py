"""
SafetyBuddy — Flask entry point.
Usage:  python run.py
"""
import os
from src.ui.flask_app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 6768))
    # Use 'stat' reloader to avoid watchdog scanning site-packages
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
        use_reloader=True,
        reloader_type="stat",
        extra_files=[os.path.join("src", "ui", "templates")],
    )
