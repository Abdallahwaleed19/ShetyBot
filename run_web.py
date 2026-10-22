"""
run_web.py — Convenience launcher for the FastAPI verification web app.
Usage: python run_web.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from config import WEB_HOST, WEB_PORT

if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=True,
        log_level="info",
    )
