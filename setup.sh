#!/bin/bash
# ================================================================
#  setup.sh — SehtyBot VPS Setup Script
#  Run as root on Ubuntu 22.04
#  Usage: bash setup.sh
# ================================================================
set -e

PROJECT_DIR="/opt/sehtybot"
SERVICE_USER="root"
PYTHON="python3.11"

echo "================================================"
echo "  SehtyBot VPS Setup"
echo "================================================"

# ── 1. System update ─────────────────────────────────────────────
echo "[1/8] Updating system..."
apt update && apt upgrade -y
apt install -y git curl wget nano software-properties-common

# ── 2. Python 3.11 ───────────────────────────────────────────────
echo "[2/8] Installing Python 3.11..."
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install -y python3.11 python3.11-pip python3.11-venv python3.11-dev

# ── 3. MariaDB ───────────────────────────────────────────────────
echo "[3/8] Installing MariaDB..."
apt install -y mariadb-server mariadb-client
systemctl start mariadb
systemctl enable mariadb

# ── 4. Clone project ─────────────────────────────────────────────
echo "[4/8] Cloning project..."
if [ -d "$PROJECT_DIR" ]; then
    echo "Directory exists, pulling latest..."
    cd "$PROJECT_DIR" && git pull
else
    git clone https://github.com/YOUR_GITHUB_USERNAME/sehtybot.git "$PROJECT_DIR"
fi

# ── 5. Python virtual environment ────────────────────────────────
echo "[5/8] Setting up Python environment..."
cd "$PROJECT_DIR"
$PYTHON -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ── 6. Create directories ────────────────────────────────────────
echo "[6/8] Creating directories..."
mkdir -p "$PROJECT_DIR/reports"
mkdir -p "$PROJECT_DIR/uploads"
mkdir -p "$PROJECT_DIR/pdf/fonts"

# ── 7. Setup MySQL database ──────────────────────────────────────
echo "[7/8] Setting up database..."
echo "Please enter a strong password for the database user:"
read -s DB_PASS

mysql -u root -e "CREATE DATABASE IF NOT EXISTS seha_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "CREATE USER IF NOT EXISTS 'seha_user'@'localhost' IDENTIFIED BY '$DB_PASS';"
mysql -u root -e "GRANT ALL PRIVILEGES ON seha_db.* TO 'seha_user'@'localhost';"
mysql -u root -e "FLUSH PRIVILEGES;"

# Create the sick_leave_reports table
mysql -u root seha_db << 'EOF'
CREATE TABLE IF NOT EXISTS `sick_leave_reports` (
  `id` bigint(20) UNSIGNED NOT NULL AUTO_INCREMENT,
  `service_code` varchar(50) NOT NULL,
  `report_type` varchar(100) NOT NULL,
  `admission_date` date NOT NULL,
  `discharge_date` date NOT NULL,
  `leave_duration_days` smallint(5) UNSIGNED NOT NULL,
  `issue_date` date NOT NULL,
  `report_time` time DEFAULT NULL,
  `national_id` varchar(14) NOT NULL,
  `patient_name_ar` varchar(200) NOT NULL,
  `patient_name_en` varchar(200) DEFAULT NULL,
  `nationality` varchar(100) DEFAULT NULL,
  `employer` varchar(200) DEFAULT NULL,
  `practitioner_name_ar` varchar(200) DEFAULT NULL,
  `practitioner_name_en` varchar(200) DEFAULT NULL,
  `job_title_ar` varchar(200) DEFAULT NULL,
  `job_title_en` varchar(200) DEFAULT NULL,
  `hospital_name_ar` varchar(200) DEFAULT NULL,
  `hospital_name_en` varchar(200) DEFAULT NULL,
  `hospital_type` enum('government','private') DEFAULT NULL,
  `hospital_logo_path` varchar(255) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `companion_name` varchar(255) DEFAULT NULL,
  `relationship` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `sick_leave_reports_service_code_unique` (`service_code`),
  UNIQUE KEY `sick_leave_reports_national_id_service_code_unique` (`national_id`,`service_code`),
  KEY `sick_leave_reports_national_id_index` (`national_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
EOF

echo "Database setup complete!"

# ── 8. Create .env file ──────────────────────────────────────────
echo "[8/8] Creating .env file..."
cat > "$PROJECT_DIR/.env" << EOF
BOT_TOKEN=PUT_YOUR_BOT_TOKEN_HERE

DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=seha_db
DB_USER=seha_user
DB_PASS=$DB_PASS

WEBAPP_URL=PUT_CLOUDFLARE_URL_HERE

WEB_HOST=0.0.0.0
WEB_PORT=8000

PROXY_URL=
EOF

echo ""
echo "================================================"
echo "  Setup complete!"
echo "  Now run: bash install_services.sh"
echo "================================================"
