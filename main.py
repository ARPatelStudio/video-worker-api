from fastapi import FastAPI, Form, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import shutil
import uuid
import time
import json
import base64
from typing import List
from gradio_client import Client

# MoviePy for Video Generation
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips

app = FastAPI()

# --- ENVIRONMENT VARIABLES ---
HF_TOKEN = os.getenv("HF_TOKEN") 

# Background memory
jobs = {}

# =====================================================================
# 🛠️ NEW FEATURE (2026 AI-FIRST): MEMORY-TO-MEMORY BASE64 MERGING
# =====================================================================

# Pydantic schema JSON payload ko securely validate karne ke liye
class Base64MergeRequest(BaseModel):
    audio_base64: str
    images_base64: List[str]
    subtitles: List[str]

@app.post("/merge-video-base64")
async def merge_video_base64(request: Base64MergeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "video_path": ""}
    
    # Render server par temporary working directory banayenge
    work_dir = f"/tmp/workspace_{job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        # 1. Base64 Audio ko wapas file mein convert karo
        audio_path = os.path.join(work_dir, "audio.wav")
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(request.audio_base64))
            
        # 2. Base64 Images ko wapas file mein convert karo
        saved_images = []
        for i, img_b64 in enumerate(request.images_base64):
            img_path = os.path.join(work_dir, f"scene_{i}.jpg")
            with open(img_path, "wb") as f:
                f.write(base64.b64decode(img_b64))
            saved_images.append(img_path)
            
        # 3. Background mein MoviePy merging engine start karo
        background_tasks.add_task(create_merged_video_task, job_id, saved_images, audio_path, request.subtitles)
        
        return {
            "job_id": job_id, 
            "message": "Base64 Payload safely received! In-memory processing started.",
            "check_status_url": f"/check-video/{job_id}",
            "download_url": f"/download-video/{job_id}"
        }
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        return {"error": f"Base64 decoding ya save karne mein error aaya: {str(e)}"}


# =====================================================================
# 🛠️ FEATURE 1: OLD FILE UPLOAD MERGING (PRESERVED)
# =====================================================================

def create_merged_video_task(job_id: str, images_paths: list, audio_path: str, subtitles_list: list):
    try:
        print(f"🎬 [{job_id}] Video Merging start ho gayi hai...")
        
        audio_clip = AudioFileClip(audio_path)
        total_duration = audio_clip.duration
        num_images = len(images_paths)
        duration_per_image = total_duration / num_images
        
        video_clips = []
        target_resolution = (720, 1280) 
        
        for i, img_path in enumerate(images_paths):
            img_clip = ImageClip(img_path).set_duration(duration_per_image)
            img_clip = img_clip.resize(height=target_resolution[1], width=target_resolution[0])
            
            # Zoom In aur Zoom Out alternate effect
            if i % 2 == 0:
                img_clip = img_clip.resize(lambda t: 1 + 0.05 * (t / duration_per_image))
            else:
                img_clip = img_clip.resize(lambda t: 1.05 - 0.05 * (t / duration_per_image))
                
            img_clip = img_clip.crop(x_center=img_clip.w/2, y_center=img_clip.h/2, 
                                     width=target_resolution[0], height=target_resolution[1])

            text = subtitles_list[i] if i < len(subtitles_list) else ""
            txt_clip = TextClip(text, fontsize=60, color='yellow', font='Liberation-Sans-Bold',
                                stroke_color='black', stroke_width=2.5, method='caption',
                                size=(target_resolution[0] * 0.85, None))
            
            txt_clip = txt_clip.set_position(('center', 0.75), relative=True).set_duration(duration_per_image)
            
            final_scene = CompositeVideoClip([img_clip, txt_clip])
            video_clips.append(final_scene)

        final_video = concatenate_videoclips(video_clips, method="compose")
        final_video = final_video.set_audio(audio_clip)
        
        os.makedirs("/tmp/ai_videos", exist_ok=True)
        output_path = f"/tmp/ai_videos/merged_{job_id}.mp4"
        
        final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", 
                                    preset="ultrafast", threads=4)
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["video_path"] = output_path
        print(f"✅ [{job_id}] Video Merge hokar Taiyar hai!")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        print(f"❌ Error in merging {job_id}: {e}")

@app.post("/merge-video")
async def merge_video(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    images: List[UploadFile] = File(...),
    subtitles_json: str = Form(...) 
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "video_path": ""}
    
    work_dir = f"/tmp/workspace_{job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    audio_path = os.path.join(work_dir, audio.filename)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
        
    saved_images = []
    for img in images:
        img_path = os.path.join(work_dir, img.filename)
        with open(img_path, "wb") as buffer:
            shutil.copyfileobj(img.file, buffer)
        saved_images.append(img_path)
    
    saved_images.sort()
    subtitles_list = json.loads(subtitles_json)
    
    background_tasks.add_task(create_merged_video_task, job_id, saved_images, audio_path, subtitles_list)
    
    return {
        "job_id": job_id, 
        "check_status_url": f"/check-video/{job_id}",
        "download_url": f"/download-video/{job_id}"
    }

# =====================================================================
# 🛠️ FEATURE 2: WAN AI VIP VIDEO GENERATOR (PRESERVED)
# =====================================================================

def generate_video_task(job_id: str, prompt: str):
    try:
        if not HF_TOKEN:
            jobs[job_id]["status"] = "failed"
            return
        client = Client("Wan-AI/Wan2.1", hf_token=HF_TOKEN)
        client.predict(prompt=prompt, size="720*1280", watermark_wan=False, seed=-1, api_name="/t2v_generation_async")

        generated_video_path = None
        for _ in range(120):  
            time.sleep(10)  
            try:
                status = client.predict(api_name="/status_refresh")
                if status and len(status) > 0 and isinstance(status[0], dict) and status[0].get("video"):
                    generated_video_path = status[0]["video"]
                    break
            except Exception:
                pass

        if generated_video_path and os.path.exists(generated_video_path):
            os.makedirs("/tmp/ai_videos", exist_ok=True)
            final_path = f"/tmp/ai_videos/{job_id}.mp4"
            shutil.copy(generated_video_path, final_path)
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["video_path"] = final_path
        else:
            jobs[job_id]["status"] = "failed"

    except Exception as e:
        jobs[job_id]["status"] = "failed"

@app.post("/start-video")
async def start_video(background_tasks: BackgroundTasks, prompt: str = Form(...)):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "video_path": ""}
    background_tasks.add_task(generate_video_task, job_id, prompt)
    return {"job_id": job_id, "check_status_url": f"/check-video/{job_id}", "download_url": f"/download-video/{job_id}"}

# =====================================================================
# 🛠️ GENERAL ENDPOINTS
# =====================================================================

@app.get("/")
def home():
    return {"status": "✅ VIP API is Live! (Base64 + In-Memory processing active)"}

@app.get("/check-video/{job_id}")
def check_video(job_id: str):
    if job_id not in jobs:
        return {"error": "Job ID nahi mili."}
    return {"status": jobs[job_id]["status"]}

@app.get("/download-video/{job_id}")
def download_video(job_id: str):
    if job_id in jobs:
        if jobs[job_id]["status"] == "completed":
            return FileResponse(jobs[job_id]["video_path"], media_type="video/mp4", filename=f"Final_Video_{job_id}.mp4")
        elif jobs[job_id]["status"] == "processing":
            return {"message": "Video process ho rahi hai."}
        else:
            return {"error": "Video fail ho gayi."}
    return {"error": "Job ID nahi mili!"}
