# ── Base image ────────────────────────────────────────────────────
FROM python:3.11-slim

# ── System dependencies (for aiomysql, reportlab, pillow) ────────
RUN apt-get update && apt-get install -y \
    gcc \
    libmariadb-dev \
    pkg-config \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies first (for layer caching) ────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy project files ────────────────────────────────────────────
COPY . .

# ── Create required directories ───────────────────────────────────
RUN mkdir -p reports uploads pdf/fonts

# ── Expose port ───────────────────────────────────────────────────
EXPOSE 8080

# ── Start both bot + web server ───────────────────────────────────
CMD ["python", "start.py"]
