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
# Image: ghcr.io/necron-99/compliance-api:latest
# Port:  8000
# =============================================================================

# Stage 1 — build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2 — minimal runtime image
FROM python:3.12-slim AS runtime

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY --from=builder /build/venv /app/venv

# Rewrite shebangs from builder path to runtime path
RUN find /app/venv/bin -type f | xargs grep -l "#!/build/venv" 2>/dev/null | \
    xargs sed -i 's|#!/build/venv|#!/app/venv|g'

ENV PATH="/app/venv/bin:$PATH"

COPY main.py .

RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log"]
