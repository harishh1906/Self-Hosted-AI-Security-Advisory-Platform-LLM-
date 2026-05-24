FROM python:3.11-slim

# Security & Optimization: Prevent .pyc files and enable real-time logging
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Create non-root user and home directory for model caching
RUN groupadd -r virtue && useradd -r -g virtue -m virtue
ENV HOME=/home/virtue

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY migrations ./migrations

# Pre-download the sentence-transformers embedding model at build time
# Avoids first-request latency spike and ensures offline capability
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Set ownership and switch to non-root user
RUN chown -R virtue:virtue /app /home/virtue
USER virtue

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Single uvicorn worker — serializes LLM calls to prevent GPU VRAM contention
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "300"]
