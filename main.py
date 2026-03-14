import os
import uuid
import shutil
import subprocess
import threading
import traceback
from typing import List

from fastapi import FastAPI, Form, File, UploadFile
from fastapi.responses import FileResponse

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

app = FastAPI()
jobs = {}

@app.get("/")
def home():
    return {"status": "✅ AI Video Worker Running (Lightning Fast - No API Limits)"}

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
# FAST CINEMATIC VIDEO PROCESSING
# =========================
def process_video(job_id, image_paths, audio_path):
    try:
        print(f"🎬 [{job_id}] Starting Cinematic Video Merge")
        workspace = f"/tmp/work_{job_id}"
        
        # 1. Prepare Audio
        audio_path = fix_audio(audio_path)
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        per_image = duration / max(1, len(image_paths))
        clips = []

        # 2. Process Background Images (Zoom & Fade)
        for i, img in enumerate(image_paths):
            clip = ImageClip(img).set_duration(per_image)
            
            # Base Resolution Setup
            clip = clip.resize(height=1400) 
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)

            # Smooth Alternate Zoom In & Out
            if i % 2 == 0:
                clip = clip.resize(lambda t: 1 + 0.04 * (t / per_image)) # Zoom In
            else:
                clip = clip.resize(lambda t: 1.04 - 0.04 * (t / per_image)) # Zoom Out
            
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)

            # Cinematic Effects
            clip = clip.fx(vfx.colorx, 1.05) 
            clip = clip.fadein(0.3).fadeout(0.3)

            clips.append(clip)

        # 3. Merge Clips
        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio_clip)

        output = f"{workspace}/output.mp4"

        # 4. Fast CPU Export
        print(f"🚀 [{job_id}] Rendering Final MP4...")
        video.write_videofile(
            output, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac", 
            preset="ultrafast", 
            threads=1
        )

        jobs[job_id] = {"status":"completed", "file":output}
        print(f"✅ [{job_id}] Video ready successfully!")

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
    text: str = Form(default="") # n8n text bhejega par hum use safely ignore karenge
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status":"processing"}
    workspace = f"/tmp/work_{job_id}"
    os.makedirs(workspace, exist_ok=True)

    # Save Audio
    audio_path = os.path.join(workspace, audio.filename)
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    # Save Images
    saved_images = []
    for i, img in enumerate(images):
        img_path = os.path.join(workspace, f"img_{i}.png")
        with open(img_path, "wb") as f:
            shutil.copyfileobj(img.file, f)
        saved_images.append(img_path)

    # Start Background Thread
    threading.Thread(target=process_video, args=(job_id, saved_images, audio_path)).start()

    return {
        "job_id": job_id, 
        "check_url": f"/check-video/{job_id}", 
        "download_url": f"/download-video/{job_id}"
    }

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
