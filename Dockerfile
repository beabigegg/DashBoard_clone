# ============================================================
# Single stage: Python runtime (frontend pre-built locally)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Install supervisor
RUN pip install --no-cache-dir supervisor

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY data/ ./data/
COPY shared/ ./shared/
COPY gunicorn.conf.py .
COPY supervisord.conf .

# Create writable runtime directories
RUN mkdir -p /app/logs /app/tmp/query_spool

ENV PYTHONPATH=/app/src

EXPOSE 8080

CMD ["supervisord", "-c", "/app/supervisord.conf"]
