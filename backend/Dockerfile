# ── Build stage ───────────────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# Create non-root user
RUN groupadd -r bookquiz && useradd -r -g bookquiz bookquiz

COPY --from=builder /root/.local /home/bookquiz/.local
COPY . .

# Ensure scripts in .local are usable
ENV PATH=/home/bookquiz/.local/bin:$PATH

RUN chown -R bookquiz:bookquiz /app
USER bookquiz

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
