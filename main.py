from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from moviepy.editor import VideoFileClip, concatenate_videoclips
import os
import shutil
import uuid

app = FastAPI()

# Temporary files delete karne ka function (Memory bachane ke liye)
def cleanup_files(folder_path):
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            print(f"Cleanup done: {folder_path}")
        except Exception as e:
            print(f"Error deleting folder: {e}")

@app.get("/")
def home():
    return {"status": "✅ Video Worker is Running perfectly!"}

@app.post("/merge-videos")
async def merge_videos(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    format: str = Form("vertical")  # Default 'vertical' (Shorts)
):
    # Har request ke liye unique folder banayein
    session_id = str(uuid.uuid4())
    temp_dir = f"/tmp/{session_id}"
    os.makedirs(temp_dir, exist_ok=True)
    
    saved_paths = []
    clips = []

    try:
        print(f"Processing {len(files)} videos for format: {format}")

        # 1. Videos save karein
        for i, file in enumerate(files):
            file_path = f"{temp_dir}/input_{i}.mp4"
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(file_path)
            
            # Clip load karein
            clip = VideoFileClip(file_path)
            
            # 2. Resize Logic (Veo 3 videos ko adjust karna)
            if format == "vertical":
                # Shorts (9:16) - Agar wide hai to crop karo, warna resize
                if clip.w > clip.h:
                    target_ratio = 9/16
                    new_width = clip.h * target_ratio
                    # Center Crop
                    clip = clip.crop(x1=clip.w/2 - new_width/2, width=new_width, height=clip.h)
                    clip = clip.resize(height=1920)
                else:
                    clip = clip.resize(height=1920)
            
            elif format == "horizontal":
                # Long Video (16:9)
                clip = clip.resize(height=1080)

            clips.append(clip)

        # 3. Merge Process
        final_clip = concatenate_videoclips(clips, method="compose")
        output_path = f"{temp_dir}/final_output.mp4"
        
        # Fast Rendering Settings (CPU bachaane ke liye)
        final_clip.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset="ultrafast", 
            threads=4
        )

        # Clips close karein
        for clip in clips:
            clip.close()

        # 4. Background Task: File bhejne ke baad delete kar dena
        background_tasks.add_task(cleanup_files, temp_dir)

        # 5. Video wapas bhejein
        return FileResponse(output_path, media_type="video/mp4", filename="merged_video.mp4")

    except Exception as e:
        print(f"Error: {e}")
        # Agar error aaye to bhi safai karo
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"error": str(e)}
