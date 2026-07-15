# Titan production image — Phase 10.1 readiness / Phase 10.2 Railway deployment
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TITAN_APP_ENV=production \
    TITAN_WEB_ENABLED=true \
    TITAN_WEB_HOST=0.0.0.0 \
    TITAN_COOKIE_SECURE=true

WORKDIR /app

RUN groupadd --system titan && useradd --system --gid titan --home-dir /app titan

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs && chown -R titan:titan /app

USER titan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/health', timeout=3)"

CMD ["python", "main.py", "web-prod"]
