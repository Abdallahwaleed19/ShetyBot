"""
run_bot.py — Convenience launcher for the Telegram bot.
Usage: python run_bot.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bot.main import main

if __name__ == "__main__":
    main()
