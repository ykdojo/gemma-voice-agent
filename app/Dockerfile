FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Kokoro model weights into the image so cold starts don't fetch them
RUN python -c "from kokoro import KPipeline; KPipeline(lang_code='a')" || true

COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "300", "server:app"]
