FROM python:3.11.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TF_CPP_MIN_LOG_LEVEL=2

WORKDIR /app

COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt

# models are mounted at runtime
COPY alembic.ini pyproject.toml ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh ./

RUN useradd --system --uid 10001 --home-dir /app dermalab \
    && mkdir -p /var/lib/dermalab/storage \
    && chown -R dermalab /var/lib/dermalab \
    && chmod +x docker-entrypoint.sh
USER dermalab

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
# one worker: the model is loaded per process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
