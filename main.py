import os
import uuid
import shutil
import subprocess
import threading
import traceback
from typing import List

from fastapi import FastAPI, Form, File, UploadFile
from fastapi.responses import FileResponse
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont

# =========================
# Pillow compatibility fix (Pillow 10+)
# =========================
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

app = FastAPI()
jobs = {}

@app.get("/")
def home():
    return {"status": "AI Video Worker Running"}

# =========================
# Audio Fix
# =========================
def fix_audio(input_path):
    output = input_path + "_fixed.wav"
    cmd = ["ffmpeg", "-y", "-i", input_path, "-ac", "2", "-ar", "44100", output]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        print(f"⚠️ FFmpeg Error: {res.stderr.decode('utf-8', errors='ignore')}")
        return input_path
    return output

# =========================
# Create Text Image
# =========================
def create_text_overlay(text, width=720, height=1280):
    img = Image.new("RGBA", (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("LiberationSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0,0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (width - text_w) // 2
    y = height - text_h - 150
    draw.text((x,y), text, font=font, fill=(255,255,0,255))
    
    path = f"/tmp/subtitle_{uuid.uuid4().hex}.png"
    img.save(path)
    return path

# =========================
# Video Processing Task
# =========================
def process_video(job_id, image_paths, audio_path, text):
    try:
        print(f"🎬 [{job_id}] Starting video merge")
        workspace = f"/tmp/work_{job_id}"
        
        # Audio Fix
        audio_path = fix_audio(audio_path)
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        per_image = duration / len(image_paths)
        clips = []

        for img in image_paths:
            clip = ImageClip(img).set_duration(per_image)
            clip = clip.resize(height=1280)
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio_clip)

        # Subtitle overlay
        subtitle_img = create_text_overlay(text)
        txt_clip = ImageClip(subtitle_img).set_duration(video.duration).set_position(("center","bottom"))

        final = CompositeVideoClip([video, txt_clip])
        output = f"{workspace}/output.mp4"

        final.write_videofile(output, fps=24, codec="libx264", audio_codec="aac", preset="ultrafast", threads=1)

        jobs[job_id] = {"status":"completed", "file":output}
        print(f"✅ [{job_id}] Video ready")

    except Exception as e:
        print(f"❌ Error {job_id}: {e}")
        traceback.print_exc()
        jobs[job_id] = {"status":"failed", "error":str(e)}

# =========================
# MULTIPART FILE UPLOAD API (The Fix)
# =========================
@app.post("/merge-video")
def merge_video_file(
    audio: UploadFile = File(...),
    images: List[UploadFile] = File(...),
    text: str = Form(...)
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status":"processing"}
    workspace = f"/tmp/work_{job_id}"
    os.makedirs(workspace, exist_ok=True)

    # Save Audio File Directly (No Base64 corruption)
    audio_path = os.path.join(workspace, audio.filename)
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    # Save Image Files Directly
    saved_images = []
    for i, img in enumerate(images):
        img_path = os.path.join(workspace, f"img_{i}.png")
        with open(img_path, "wb") as f:
            shutil.copyfileobj(img.file, f)
        saved_images.append(img_path)

    # Process in background
    threading.Thread(target=process_video, args=(job_id, saved_images, audio_path, text)).start()

    return {"job_id": job_id, "check_url": f"/check-video/{job_id}", "download_url": f"/download-video/{job_id}"}

# =========================
# Status & Download
# =========================
@app.get("/check-video/{job_id}")
def check(job_id:str):
    if job_id not in jobs:
        return {"status":"not_found"}
    return {"status": jobs[job_id]["status"]}

@app.get("/download-video/{job_id}")
def download(job_id:str):
    if job_id not in jobs:
        return {"error":"job not found"}
    if jobs[job_id]["status"] != "completed":
        return {"status":"processing"}
    return FileResponse(jobs[job_id]["file"], media_type="video/mp4", filename="video.mp4")
