# ==============================
# Base Image (Python 3.11 - Most Stable for AI)
# ==============================
FROM python:3.11-slim

# ==============================
# System Dependencies Install
# ==============================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    fonts-liberation \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# ==============================
# Set Working Directory
# ==============================
WORKDIR /app

# ==============================
# Copy requirements
# ==============================
COPY requirements.txt .

# ==============================
# Install Python Dependencies
# ==============================
RUN pip install --no-cache-dir -r requirements.txt

# ==============================
# Copy Project Files
# ==============================
COPY . .

# ==============================
# Expose Port
# ==============================
EXPOSE 10000

# ==============================
# Start FastAPI Server
# ==============================
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
