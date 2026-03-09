# 2026 Modern Standard: Python 3.12 version use karenge (More stable, secure aur fast hai)
FROM python:3.12-slim

# 1. System updates aur FFmpeg install karein
RUN apt-get update && \
    apt-get install -y ffmpeg libsm6 libxext6 && \
    rm -rf /var/lib/apt/lists/*

# 2. Work directory set karein
WORKDIR /app

# 3. Python libraries install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Saara code copy karein
COPY . .

# 5. Server start command (Render ke dynamic $PORT environment variable ko support karne ke liye)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
