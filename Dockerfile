# --- Stage 1: Build dependencies ---
FROM python:3.10-slim AS builder

WORKDIR /app

# Install system deps for faiss-cpu and numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Production image ---
FROM python:3.10-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ src/
COPY static/ static/

# Create directories for runtime data
RUN mkdir -p /app/data /app/logs

# data/ is mounted as a volume (contains content.db, vectors.faiss, id_map.pkl)
# logs/ is mounted as a volume

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run with production settings
# Workers = (2 * CPU_cores) + 1 for CPU-bound FAISS workloads
# Use --workers 1 because FAISS index + ML model are loaded per-worker (memory heavy)
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
