FROM python:3.12-slim

# Install tesseract-ocr (Bangla + English) and ffmpeg (for whisper)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-ben tesseract-ocr-eng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY social-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY social-engine/ /app/

EXPOSE 9800

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9800"]
