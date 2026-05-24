FROM python:3.11-slim

WORKDIR /app

# Security: non-root user
RUN useradd -m -r fetcher && \
    mkdir -p /data/knowledge-inbox && \
    chown -R fetcher:fetcher /data/knowledge-inbox

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fetcher/ ./fetcher/

USER fetcher

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; assert os.path.isdir('/data/knowledge-inbox')"

CMD ["python", "-m", "fetcher.main"]
