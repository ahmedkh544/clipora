FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements-studio.txt ./
RUN pip install --no-cache-dir -r requirements-studio.txt

COPY . .
RUN mkdir -p studio_uploads studio_output studio_broll

ENV PORT=8765 CLIPORA_STORAGE_ROOT=/data
RUN mkdir -p /data/uploads /data/outputs
EXPOSE 8765
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 3600 studio_app:app"]
