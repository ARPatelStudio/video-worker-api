from fastapi import FastAPI, Form
from fastapi.responses import FileResponse
import os
import shutil
import uuid
import time
import threading
from gradio_client import Client

app = FastAPI()

# Background memory
jobs = {}

def generate_video_task(job_id: str, prompt: str):
    try:
        print(f"🚀 [{job_id}] Wan 2.1 AI ko order bhej diya: {prompt}")
        client = Client("Wan-AI/Wan2.1")
        
        # Start generation
        client.predict(
            prompt=prompt,
            size="720*1280",
            watermark_wan=False,
            seed=-1,
            api_name="/t2v_generation_async"
        )

        # Smart Polling (Waiting for video)
        generated_video_path = None
        for _ in range(120):  # Maximum 20 minute wait
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
            print(f"✅ [{job_id}] Video Bankar Taiyar! URL se download kar sakte hain.")
        else:
            jobs[job_id]["status"] = "failed"
            print(f"❌ [{job_id}] Video nahi ban payi, HF par bheed hai.")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        print(f"❌ Error in {job_id}: {e}")

@app.get("/")
def home():
    return {"status": "✅ Video Generator Test Mode is Live!"}

# --- 1. VIDEO BANANE KA ORDER DO ---
@app.post("/start-video")
async def start_video(prompt: str = Form(...)):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "video_path": ""}
    
    # Background thread start
    thread = threading.Thread(target=generate_video_task, args=(job_id, prompt))
    thread.start()
    
    return {
        "job_id": job_id, 
        "message": "Background mein video ban rahi hai. 5-10 minute baad check karein!",
        "check_status_url": f"/check-video/{job_id}",
        "download_url": f"/download-video/{job_id}"
    }

# --- 2. STATUS CHECK KARO ---
@app.get("/check-video/{job_id}")
def check_video(job_id: str):
    if job_id not in jobs:
        return {"error": "Job ID nahi mili"}
    return {"status": jobs[job_id]["status"]}

# --- 3. VIDEO BROWSER MEIN DEKHO/DOWNLOAD KARO ---
@app.get("/download-video/{job_id}")
def download_video(job_id: str):
    if job_id in jobs and jobs[job_id]["status"] == "completed":
        return FileResponse(jobs[job_id]["video_path"], media_type="video/mp4", filename="Wan_Test.mp4")
    return {"error": "Video abhi tak ready nahi hui hai ya fail ho gayi hai!"}
