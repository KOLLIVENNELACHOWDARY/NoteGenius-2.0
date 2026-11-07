# NoteGenius container. Works on Hugging Face Spaces, Render, Railway, Fly.io, or any Docker host.
#   Lite build (default, runs in 512 MB RAM, every tool works):  docker build -t notegenius .
#   Full build (adds neural models, needs ~2 GB RAM):            docker build --build-arg INSTALL_ML=1 -t notegenius .
FROM python:3.11-slim

ARG INSTALL_ML=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/local/share/nltk_data \
    HF_HOME=/opt/hf-cache \
    DATA_DIR=/tmp/notegenius \
    PORT=7860

# tesseract = text recognition for scanned PDFs/photos, graphviz = mind maps, libgomp1 = PyTorch runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr graphviz libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
# CPU-only PyTorch is ~2 GB smaller than the default CUDA build.
RUN if [ "$INSTALL_ML" = "1" ]; then \
      pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements-ml.txt; \
    else \
      pip install -r requirements.txt; \
    fi

RUN python -m nltk.downloader -d "$NLTK_DATA" stopwords punkt punkt_tab wordnet omw-1.4

# Download the neural models at build time so the first visitor does not wait (skipped if offline).
COPY scripts/download_models.py scripts/
RUN if [ "$INSTALL_ML" = "1" ]; then python scripts/download_models.py; fi \
 && mkdir -p "$HF_HOME" && chmod -R a+rwX "$HF_HOME"

COPY . .
RUN useradd -m -u 1000 app && mkdir -p "$DATA_DIR" && chown -R app /app "$DATA_DIR"
USER app

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','7860'))"
# PORT is provided by the host (Render, Cloud Run) or defaults to 7860.
# One worker: models load once and visitor data lives on local disk. Threads handle concurrency.
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300 app:app
