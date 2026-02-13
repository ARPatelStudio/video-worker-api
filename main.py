from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
# CHANGE 1: 'moviepy.editor' ab exist nahi karta, direct import karein
from moviepy import VideoFileClip, concatenate_videoclips
import os
import shutil
import uuid

app = FastAPI()

# Temporary files safai abhiyian
def cleanup_files(folder_path):
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            print(f"Cleanup done: {folder_path}")
        except Exception as e:
            print(f"Error deleting folder: {e}")

@app.get("/")
def home():
    return {"status": "✅ Video Worker (MoviePy v2.2.1) is Live!"}

@app.post("/merge-videos")
async def merge_videos(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    format: str = Form("vertical")
):
    session_id = str(uuid.uuid4())
    temp_dir = f"/tmp/{session_id}"
    os.makedirs(temp_dir, exist_ok=True)
    
    saved_paths = []
    clips = []

    try:
        print(f"Processing {len(files)} videos with MoviePy v2.2.1...")

        # 1. Videos Save Logic
        for i, file in enumerate(files):
            file_path = f"{temp_dir}/input_{i}.mp4"
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_paths.append(file_path)
            
            # Clip Load
            clip = VideoFileClip(file_path)
            
            # 2. Resizing Logic (Updated for v2)
            # Dhyan dein: Ab '.resize()' nahi '.resized()' use hota hai
            
            if format == "vertical":
                # Shorts Logic (9:16)
                if clip.w > clip.h:
                    target_ratio = 9/16
                    new_width = clip.h * target_ratio
                    
                    # CHANGE 2: .crop() -> .cropped()
                    clip = clip.cropped(
                        x1=clip.w/2 - new_width/2, 
                        width=new_width, 
                        height=clip.h
                    )
                    
                    # CHANGE 3: .resize() -> .resized()
                    clip = clip.resized(height=1920)
                else:
                    clip = clip.resized(height=1920)
            
            elif format == "horizontal":
                # Long Video Logic
                clip = clip.resized(height=1080)

            clips.append(clip)

        # 3. Merging Logic
        final_clip = concatenate_videoclips(clips, method="compose")
        output_path = f"{temp_dir}/final_output.mp4"
        
        # 4. Rendering
        # 'preset' aur 'threads' fast rendering ke liye zaruri hain
        final_clip.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset="ultrafast", 
            threads=4
        )

        # Cleanup Memory
        for clip in clips:
            clip.close()
        final_clip.close()

        # Background Cleanup Task
        background_tasks.add_task(cleanup_files, temp_dir)

        return FileResponse(output_path, media_type="video/mp4", filename="merged_video.mp4")

    except Exception as e:
        # Error handling
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"error": str(e), "details": "MoviePy v2 update error"}
