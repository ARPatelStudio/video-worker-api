from fastapi import FastAPI, Form, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
import os
import shutil
import uuid
import time
import json
from typing import List
from gradio_client import Client

# MoviePy for Video Generation
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

app = FastAPI()

# --- ENVIRONMENT VARIABLES ---
HF_TOKEN = os.getenv("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") 

# Background memory
jobs = {}

# =====================================================================
# 🛠️ FEATURE 1: VIDEO MERGING (IMAGES + AUDIO + SUBTITLES)
# =====================================================================

def create_merged_video_task(job_id: str, images_paths: list, audio_path: str, subtitles_list: list):
    try:
        print(f"🎬 [{job_id}] Video Merging start ho gayi hai...")
        
        # Audio load karein
        audio_clip = AudioFileClip(audio_path)
        total_duration = audio_clip.duration
        
        # Har image ka time nikalen (e.g., 30 sec / 10 images = 3 sec per image)
        num_images = len(images_paths)
        duration_per_image = total_duration / num_images
        
        video_clips = []
        target_resolution = (720, 1280) # YouTube Shorts Vertical Format
        
        for i, img_path in enumerate(images_paths):
            # 1. Image Load karein aur resize karein
            img_clip = ImageClip(img_path).set_duration(duration_per_image)
            img_clip = img_clip.resize(height=target_resolution[1], width=target_resolution[0])
            
            # 2. Animation: Zoom In aur Zoom Out alternate effect
            # Effect banane ke liye scale karte hain aur center se crop karte hain
            if i % 2 == 0:
                # Zoom In
                img_clip = img_clip.resize(lambda t: 1 + 0.05 * (t / duration_per_image))
            else:
                # Zoom Out
                img_clip = img_clip.resize(lambda t: 1.05 - 0.05 * (t / duration_per_image))
                
            # Resize ke baad original size par crop taaki frame na hile
            img_clip = img_clip.crop(x_center=img_clip.w/2, y_center=img_clip.h/2, 
                                     width=target_resolution[0], height=target_resolution[1])

            # 3. Subtitles (Captions) add karein
            text = subtitles_list[i] if i < len(subtitles_list) else ""
            txt_clip = TextClip(text, fontsize=60, color='yellow', font='Liberation-Sans-Bold',
                                stroke_color='black', stroke_width=2.5, method='caption',
                                size=(target_resolution[0] * 0.85, None))
            
            # Text ko screen ke bottom par position karein
            txt_clip = txt_clip.set_position(('center', 0.75), relative=True).set_duration(duration_per_image)
            
            # Image aur Text ko merge karein
            final_scene = CompositeVideoClip([img_clip, txt_clip])
            video_clips.append(final_scene)

        # 4. Saari scenes ko jodein
        final_video = concatenate_videoclips(video_clips, method="compose")
        final_video = final_video.set_audio(audio_clip)
        
        # 5. Final Export using FFmpeg engine
        os.makedirs("/tmp/ai_videos", exist_ok=True)
        output_path = f"/tmp/ai_videos/merged_{job_id}.mp4"
        
        # fps=24 (cinematic), preset ultrafast for server speed
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
    subtitles_json: str = Form(...)  # Expected JSON string list e.g., '["Scene 1 text", "Scene 2 text"]'
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "video_path": ""}
    
    # 1. Inputs ko server par save karein
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
    
    # Sort images by name so they are in correct order (scene_1, scene_2, etc.)
    saved_images.sort()
    
    # Parse subtitles
    subtitles_list = json.loads(subtitles_json)
    
    # Background task start karein
    background_tasks.add_task(create_merged_video_task, job_id, saved_images, audio_path, subtitles_list)
    
    return {
        "job_id": job_id, 
        "message": "Images aur Audio merging start ho gayi hai. Kuch min mein check karein!",
        "check_status_url": f"/check-video/{job_id}",
        "download_url": f"/download-video/{job_id}"
    }


# =====================================================================
# 🛠️ FEATURE 2: WAN AI VIP VIDEO GENERATOR (PURANA CODE SAFE HAI)
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
    return {
        "job_id": job_id, 
        "check_status_url": f"/check-video/{job_id}",
        "download_url": f"/download-video/{job_id}"
    }

# =====================================================================
# 🛠️ GENERAL ENDPOINTS (STATUS & DOWNLOAD)
# =====================================================================

@app.get("/")
def home():
    return {"status": "✅ VIP API is Live! (Wan AI + MoviePy Merging)"}

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
