# =============================================================================
# Compliance API Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (builder): install dependencies into a virtual environment
#   Stage 2 (runtime): copy venv into a minimal Python slim image
#
# The database is NOT included in the image — it is fetched from S3
# by the Kubernetes init container on pod start.
#
# Image: ghcr.io/rsbailey/compliance-api:latest
# Port:  8000
# =============================================================================

FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log"]















































