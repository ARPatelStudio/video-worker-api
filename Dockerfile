# Python 3.9 version use karenge (Stable aur Fast hai)
FROM python:3.9-slim

# 1. System updates aur FFmpeg install karein
# libsm6 aur libxext6 graphics processing ke liye zaruri hain
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

# 5. Server start command (Port 10000 Render ke liye best hai)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
