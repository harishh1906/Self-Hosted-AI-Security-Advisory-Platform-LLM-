FROM python:3.11-slim

WORKDIR /app

# Security: non-root user
RUN useradd -m -r ingester

# Pre-download embedding model at build time (same as advisory-api)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-cache the embedding model to avoid cold-start
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY ingester/ ./ingester/

RUN chown -R ingester:ingester /app

USER ingester

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; assert os.path.isdir(os.getenv('INBOX_PATH', '/data/knowledge-inbox'))"

CMD ["python", "-m", "ingester.main"]
