from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
import os
import shutil
import uuid
import time
from gradio_client import Client

app = FastAPI()

def cleanup_files(folder_path):
    """Temporary files aur memory ko saaf karne ka function"""
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            print(f"Cleanup done: {folder_path}")
        except Exception as e:
            print(f"Error during cleanup: {e}")

@app.get("/")
def home():
    return {"status": "✅ Ultimate AI Video Worker (Wan 2.1 + MoviePy) is Live!"}

# --- 🚀 THE MASTER FUNCTION: WAN 2.1 AI + MOVIEPY AUDIO MIXER ---
@app.post("/generate-ai-short")
async def generate_ai_short(
    background_tasks: BackgroundTasks,
    prompt: str = Form(..., description="Prompt for Wan 2.1 AI Video"),
    audio: UploadFile = File(..., description="Audio File from N8N")
):
    session_id = str(uuid.uuid4())
    temp_dir = f"/tmp/ai_shorts_{session_id}"
    os.makedirs(temp_dir, exist_ok=True)
    
    audio_path = f"{temp_dir}/story_audio.wav"
    output_path = f"{temp_dir}/final_ai_short.mp4"

    try:
        # 1. N8N se aayi Audio file ko save karna
        print("🎵 Saving Audio File...")
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        # 2. Hugging Face (Wan 2.1) API ko bulana
        print(f"🚀 Prompting Wan 2.1 API: {prompt}")
        client = Client("Wan-AI/Wan2.1")
        
        # Generation start karna (720*1280 vertical resolution ke sath)
        client.predict(
            prompt=prompt,
            size="720*1280",
            watermark_wan=False,
            seed=-1,
            api_name="/t2v_generation_async"
        )

        # 3. Smart Polling: Baar-baar check karna (Kyunki queue hoti hai)
        print("⏳ Waiting for AI Video to generate... (Isme 5-15 mins lag sakte hain)")
        generated_video_path = None
        
        # Maximum 20 minute tak wait karega (120 baar x 10 seconds)
        for _ in range(120):  
            time.sleep(10)  
            try:
                status = client.predict(api_name="/status_refresh")
                # API documentation ke hisaab se check karna
                if status and len(status) > 0 and isinstance(status[0], dict):
                    if status[0].get("video"):
                        generated_video_path = status[0]["video"]
                        break
            except Exception as wait_error:
                print(f"Still waiting... {wait_error}")
                pass

        if not generated_video_path or not os.path.exists(generated_video_path):
            raise Exception("AI took too long or failed. Hugging Face par bheed zyada hai!")

        print(f"✅ AI Video Successfully Downloaded! Path: {generated_video_path}")

        # 4. MoviePy v2 se Audio aur Video ko Mix karna
        print("🎬 Starting Audio & Video Mix...")
        video_clip = VideoFileClip(generated_video_path)
        audio_clip = AudioFileClip(audio_path)

        # Agar video vertical nahi aayi, toh 9:16 mein crop karna
        if video_clip.w > video_clip.h:
            target_ratio = 9/16
            new_width = video_clip.h * target_ratio
            video_clip = video_clip.cropped(
                x1=video_clip.w/2 - new_width/2, 
                width=new_width, 
                height=video_clip.h
            )
        video_clip = video_clip.resized(height=1920)

        # Video ko audio ki lambai ke barabar loop karna
        clips_to_concat = []
        current_dur = 0
        while current_dur < audio_clip.duration:
            clips_to_concat.append(video_clip)
            current_dur += video_clip.duration
            
        final_video = concatenate_videoclips(clips_to_concat)
        final_video = final_video.with_duration(audio_clip.duration)
        final_video = final_video.with_audio(audio_clip)

        # 5. Fast rendering
        final_video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset="ultrafast", 
            threads=4
        )

        # Memory Cleanup
        video_clip.close()
        audio_clip.close()
        final_video.close()

        # Server ka kachra saaf karne ka background task
        background_tasks.add_task(cleanup_files, temp_dir)

        return FileResponse(output_path, media_type="video/mp4", filename="Viral_AI_Short.mp4")

    except Exception as e:
        cleanup_files(temp_dir)
        return {"error": str(e), "details": "AI Process ya Merge mein error aayi."}
