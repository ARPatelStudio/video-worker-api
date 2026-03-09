# 2026 Modern Standard: Python 3.12 version
FROM python:3.12-slim

# 1. System updates, FFmpeg, ImageMagick (TextClip ke liye) aur Fonts install karein
RUN apt-get update && \
    apt-get install -y ffmpeg libsm6 libxext6 imagemagick fonts-liberation && \
    # ImageMagick ki default policy update karein taaki text render ho sake
    sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml && \
    rm -rf /var/lib/apt/lists/*

# 2. Work directory set karein
WORKDIR /app

# 3. Python libraries install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Saara code copy karein
COPY . .

# 5. Server start command (Render ke dynamic $PORT environment variable ke liye)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
