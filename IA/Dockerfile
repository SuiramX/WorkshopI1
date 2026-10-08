FROM python:3.11-slim

# Install system dependencies for OpenCV, PyTorch, V4L2 and image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    v4l-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=1000 \
    PIP_RETRIES=10 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

COPY . .

# Ensure storage directories exist for models and facial records
RUN mkdir -p /app/models /app/authorized_faces /app/blacklist

CMD ["python", "yolo_vision.py"]
