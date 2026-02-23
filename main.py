from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
import os
import shutil
import uuid

app = FastAPI()

def cleanup_files(folder_path):
    """Temporary files ko delete karne ka function"""
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            print(f"Cleanup done: {folder_path}")
        except Exception as e:
            print(f"Error deleting folder: {e}")

@app.get("/")
def home():
    return {"status": "✅ Video Worker (MoviePy v2.2.1) is Live and Ready for Shorts!"}

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
        print(f"Processing {len(files)} videos...")
        for i, file in enumerate(files):
            file_path = f"{temp_dir}/input_{i}.mp4"
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            clip = VideoFileClip(file_path)
            
            if format == "vertical":
                if clip.w > clip.h:
                    target_ratio = 9/16
                    new_width = clip.h * target_ratio
                    clip = clip.cropped(x1=clip.w/2 - new_width/2, width=new_width, height=clip.h)
                clip = clip.resized(height=1920)
            elif format == "horizontal":
                clip = clip.resized(height=1080)

            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")
        output_path = f"{temp_dir}/final_output.mp4"
        
        final_clip.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset="ultrafast", 
            threads=4
        )

        for clip in clips: 
            clip.close()
        final_clip.close()

        background_tasks.add_task(cleanup_files, temp_dir)
        return FileResponse(output_path, media_type="video/mp4", filename="merged_video.mp4")

    except Exception as e:
        cleanup_files(temp_dir)
        return {"error": str(e)}

@app.post("/add-audio")
async def add_audio_to_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Background MP4 Video"),
    audio: UploadFile = File(..., description="Generated Audio WAV/MP3")
):
    session_id = str(uuid.uuid4())
    temp_dir = f"/tmp/shorts_{session_id}"
    os.makedirs(temp_dir, exist_ok=True)
    
    video_path = f"{temp_dir}/bg_video.mp4"
    audio_path = f"{temp_dir}/story_audio.wav"
    output_path = f"{temp_dir}/final_youtube_short.mp4"

    try:
        print("🎬 Starting Audio & Video Mix...")
        
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)

        if video_clip.w > video_clip.h:
            target_ratio = 9/16
            new_width = video_clip.h * target_ratio
            video_clip = video_clip.cropped(
                x1=video_clip.w/2 - new_width/2, 
                width=new_width, 
                height=video_clip.h
            )
        video_clip = video_clip.resized(height=1920)

        clips_to_concat = []
        current_dur = 0
        while current_dur < audio_clip.duration:
            clips_to_concat.append(video_clip)
            current_dur += video_clip.duration
            
        final_video = concatenate_videoclips(clips_to_concat)
        final_video = final_video.with_duration(audio_clip.duration)
        final_video = final_video.with_audio(audio_clip)

        final_video.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            preset="ultrafast", 
            threads=4
        )

        video_clip.close()
        audio_clip.close()
        final_video.close()

        background_tasks.add_task(cleanup_files, temp_dir)

        return FileResponse(output_path, media_type="video/mp4", filename="Viral_Short.mp4")

    except Exception as e:
        cleanup_files(temp_dir)
        return {"error": str(e), "details": "Error merging audio and video for Short."}
