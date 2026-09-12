# SQLPilot — single image, two roles (API and Streamlit UI), selected by the
# compose service's command. Kept slim: ChromaDB ships its own ONNX embedder,
# so there's no torch in here.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# deps first so code edits don't bust the layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY knowledge_base/ ./knowledge_base/
COPY streamlit_app.py ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# run as non-root; /app/data is the volume mount point and must be writable
RUN chmod +x /usr/local/bin/entrypoint.sh \
    && useradd --create-home --uid 10001 sqlpilot \
    && mkdir -p /app/data \
    && chown -R sqlpilot:sqlpilot /app
USER sqlpilot

EXPOSE 8000 8501

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
