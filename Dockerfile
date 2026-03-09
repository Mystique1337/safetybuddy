FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directories exist
RUN mkdir -p data/models data/processed data/raw

EXPOSE 5000

# Use gunicorn for production; 2 workers + 120s timeout for GPT-4o / YOLO
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "run:app"]
