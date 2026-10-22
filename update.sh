#!/bin/bash
# ================================================================
#  update.sh — Pull latest code and restart services
#  Usage: bash update.sh
# ================================================================
PROJECT_DIR="/opt/sehtybot"

echo "Updating SehtyBot..."
cd "$PROJECT_DIR"

git pull

source venv/bin/activate
pip install -r requirements.txt --quiet

systemctl restart sehtybot
systemctl restart sehtybot-web

echo "Done! Services restarted."
systemctl status sehtybot --no-pager
