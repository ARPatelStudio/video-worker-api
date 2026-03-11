import os
import uuid
import shutil
import subprocess
import threading
import traceback
import textwrap
from typing import List

from fastapi import FastAPI, Form, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip
import moviepy.video.fx.all as vfx

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
    return {"status": "✅ AI Video Worker Running with Pro Effects"}

# =========================
# Audio Fix (FFmpeg)
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
# 2026 MODERN CAPTIONS (Hormozi Style)
# =========================
def create_text_overlay(text, width=720, height=1280):
    img = Image.new("RGBA", (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    
    # 1. Font setup (Agar LiberationSans na mile toh default load hoga)
    try:
        font = ImageFont.truetype("LiberationSans-Bold.ttf", 55)
    except:
        font = ImageFont.load_default()

    # 2. Text Wrapping (Bahar jaane se rokne ke liye)
    wrapper = textwrap.TextWrapper(width=22) # Ek line mein max 22 letters
    lines = wrapper.wrap(text=text)

    # 3. Calculate total height so we can center the block vertically at the bottom
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0,0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    
    total_text_height = sum(line_heights) + (15 * len(lines))
    y_start = height - total_text_height - 250 
    
    # 4. Draw each line
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x_start = (width - text_w) // 2
        
        # Black Semi-Transparent Background Box
        box_padding = 15
        draw.rectangle(
            [x_start - box_padding, y_start - box_padding, x_start + text_w + box_padding, y_start + text_h + box_padding],
            fill=(0, 0, 0, 180)
        )
        
        # Glowing Yellow Text with Black Stroke
        draw.text(
            (x_start, y_start), 
            line, 
            font=font, 
            fill=(255, 230, 0, 255), 
            stroke_width=3, 
            stroke_fill=(0, 0, 0, 255)
        )
        
        y_start += text_h + 15 
        
    path = f"/tmp/subtitle_{uuid.uuid4().hex}.png"
    img.save(path)
    return path

# =========================
# ADVANCED VIDEO PROCESSING
# =========================
def process_video(job_id, image_paths, audio_path, text):
    try:
        print(f"🎬 [{job_id}] Starting Advanced Video Merge")
        workspace = f"/tmp/work_{job_id}"
        
        audio_path = fix_audio(audio_path)
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        per_image = duration / max(1, len(image_paths))
        clips = []

        for i, img in enumerate(image_paths):
            clip = ImageClip(img).set_duration(per_image)
            
            # 1. Base Resolution Setup
            clip = clip.resize(height=1400) 
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)

            # 2. Smooth Alternate Zoom In & Out
            if i % 2 == 0:
                clip = clip.resize(lambda t: 1 + 0.04 * (t / per_image)) # Zoom In
            else:
                clip = clip.resize(lambda t: 1.04 - 0.04 * (t / per_image)) # Zoom Out
            
            # Re-crop to strict Shorts dimension
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)

            # 3. Basic Color Grading (Contrast Boost)
            clip = clip.fx(vfx.colorx, 1.05) 

            # 4. Fade In / Fade Out Transitions
            clip = clip.fadein(0.3).fadeout(0.3)

            clips.append(clip)

        # Merge all clips
        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio_clip)

        # 5. Apply Subtitles
        if text and text.strip() != "":
            subtitle_img = create_text_overlay(text)
            txt_clip = ImageClip(subtitle_img).set_duration(video.duration).set_position(("center","top"))
            final = CompositeVideoClip([video, txt_clip])
        else:
            final = video

        output = f"{workspace}/output.mp4"

        # Fast Export with libx264
        final.write_videofile(
            output, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            preset="ultrafast", 
            threads=1
        )

        jobs[job_id] = {"status":"completed", "file":output}
        print(f"✅ [{job_id}] Video ready with Pro Effects")

    except Exception as e:
        print(f"❌ Error {job_id}: {e}")
        traceback.print_exc()
        jobs[job_id] = {"status":"failed", "error":str(e)}

# =========================
# MULTIPART FILE UPLOAD API
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

    # Save Audio securely
    audio_path = os.path.join(workspace, audio.filename)
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    # Save Images securely
    saved_images = []
    for i, img in enumerate(images):
        img_path = os.path.join(workspace, f"img_{i}.png")
        with open(img_path, "wb") as f:
            shutil.copyfileobj(img.file, f)
        saved_images.append(img_path)

    # Run heavy processing in Background
    threading.Thread(target=process_video, args=(job_id, saved_images, audio_path, text)).start()

    return {
        "job_id": job_id, 
        "check_url": f"/check-video/{job_id}", 
        "download_url": f"/download-video/{job_id}"
    }

# =========================
# Check Status API
# =========================
@app.get("/check-video/{job_id}")
def check(job_id:str):
    if job_id not in jobs:
        return {"status":"not_found"}
    return {"status": jobs[job_id]["status"]}

# =========================
# Download Output API
# =========================
@app.get("/download-video/{job_id}")
def download(job_id:str):
    if job_id not in jobs:
        return {"error":"job not found"}
    if jobs[job_id]["status"] != "completed":
        return {"status":"processing"}
    return FileResponse(jobs[job_id]["file"], media_type="video/mp4", filename="video.mp4")
