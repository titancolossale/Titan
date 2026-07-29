# Titan production image — Phase 10.1 readiness / Phase 10.2 Railway deployment
# Phase 20.13 — ECAPA biometric runtime (torch / torchaudio / speechbrain CPU)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TITAN_APP_ENV=production \
    TITAN_WEB_ENABLED=true \
    TITAN_WEB_HOST=0.0.0.0 \
    TITAN_COOKIE_SECURE=true \
    TITAN_VOICE_EMBEDDING_PROVIDER=ecapa \
    TITAN_VOICE_EMBEDDING_VERSION=ecapa_v1 \
    TITAN_VOICE_BIOMETRIC_TRUST_MODE=production \
    TITAN_VOICE_EMBEDDING_REQUIRE_PRODUCTION_TRUST=true \
    TITAN_VOICE_EMBEDDING_ALLOW_DEV_IDENTITY=false \
    TITAN_VOICE_EMBEDDING_ENCRYPTION=true \
    TITAN_VOICE_EMBEDDING_RETAIN_RAW_AUDIO=false \
    TITAN_VOICE_EMBEDDING_KEY_ID=primary \
    TITAN_VOICE_ENROLLMENT_REQUIRE_CONSENT=true \
    TITAN_VOICE_ALWAYS_LISTENING=false \
    TITAN_VOICE_WAKE_WORD_ENABLED=false \
    TITAN_VOICE_ECAPA_DEVICE=cpu

WORKDIR /app

RUN groupadd --system titan && useradd --system --gid titan --home-dir /app titan

# OpenMP + libsndfile needed by torch / torchaudio CPU wheels on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip && pip install -r requirements-prod.txt

COPY . .

RUN mkdir -p /app/data /app/logs /app/data/voice_models/ecapa \
    && chown -R titan:titan /app

USER titan

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/health', timeout=3)"

CMD ["python", "main.py", "web-prod"]
