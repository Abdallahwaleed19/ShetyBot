#!/bin/bash
# ================================================================
#  install_services.sh — Install systemd services for SehtyBot
#  Run after setup.sh
# ================================================================
PROJECT_DIR="/opt/sehtybot"

echo "Installing systemd services..."

# ── Bot Service ──────────────────────────────────────────────────
cat > /etc/systemd/system/sehtybot.service << EOF
[Unit]
Description=SehtyBot - Telegram Sick Leave Bot
After=network.target mariadb.service
Wants=mariadb.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
ExecStart=$PROJECT_DIR/venv/bin/python run_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── Web Server Service ───────────────────────────────────────────
cat > /etc/systemd/system/sehtybot-web.service << EOF
[Unit]
Description=SehtyBot - FastAPI Web Server
After=network.target mariadb.service
Wants=mariadb.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
ExecStart=$PROJECT_DIR/venv/bin/python run_web.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── Enable and start ─────────────────────────────────────────────
systemctl daemon-reload
systemctl enable sehtybot sehtybot-web
systemctl start sehtybot sehtybot-web

echo ""
echo "Services installed and started!"
echo ""
echo "Check status:"
echo "  systemctl status sehtybot"
echo "  systemctl status sehtybot-web"
echo ""
echo "View logs:"
echo "  journalctl -u sehtybot -f"
echo "  journalctl -u sehtybot-web -f"
