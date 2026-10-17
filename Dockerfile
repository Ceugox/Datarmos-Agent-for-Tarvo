FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt
COPY src/ ./src/
COPY api/ ./api/
COPY config/ ./config/
COPY run_engine.py .python-version docker-entrypoint.sh ./
ENV PYTHONPATH=/app/src DATA_DIR=/data PORT=8000
RUN useradd --uid 10001 --no-create-home --home-dir /app app && mkdir -p /data && chown app:app /data && chmod +x /app/docker-entrypoint.sh
# USER stays root on purpose: the entrypoint fixes the volume ownership and then drops to the app user with runuser.
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh","-c","exec uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
