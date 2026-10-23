"""
run_web.py — FastAPI web server launcher.
Usage: python run_web.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from config import WEB_HOST, WEB_PORT

if __name__ == "__main__":
    # reload=True only in local dev, False in production
    is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"
    uvicorn.run(
        "web.app:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=is_dev,
        log_level="info",
    )
