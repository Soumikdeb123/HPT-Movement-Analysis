FROM python:3.11-slim

WORKDIR /app/backend/player_tracking

RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY hpt_tracking ./hpt_tracking
COPY yolov8x.pt ./yolov8x.pt

RUN mkdir -p /app/runtime

ENV HPT_RUNTIME_DIR=/app/runtime
ENV HPT_YOLO_MODEL=/app/backend/player_tracking/yolov8x.pt
ENV HPT_INFERENCE_DEVICE=cpu
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn hpt_tracking.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
