from fastapi import FastAPI, Form, File, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import shutil
import uuid
import json
import base64
import subprocess
from typing import List

# ================================
# Pillow ANTIALIAS fix (2026)
# ================================
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

# MoviePy
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips
)

app = FastAPI()

jobs = {}

# ====================================================
# BASE64 CLEANER
# ====================================================

def clean_base64_string(b64_string: str) -> bytes:

    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]

    b64_string += "=" * ((4 - len(b64_string) % 4) % 4)

    return base64.b64decode(b64_string)


# ====================================================
# AUDIO AUTO FIX USING FFMPEG
# ====================================================

def ensure_valid_audio(input_path):

    fixed_path = input_path + "_fixed.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "2",
        "-ar", "44100",
        fixed_path
    ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return fixed_path


# ====================================================
# VIDEO MERGE BACKGROUND TASK
# ====================================================

def create_merged_video_task(job_id, images_paths, audio_path, subtitles):

    try:

        print(f"🎬 [{job_id}] Video merging started")

        audio_path = ensure_valid_audio(audio_path)

        audio_clip = AudioFileClip(audio_path)

        total_duration = audio_clip.duration

        num_images = len(images_paths)

        duration_per_image = total_duration / num_images

        video_clips = []

        target_resolution = (720, 1280)

        for i, img_path in enumerate(images_paths):

            img_clip = ImageClip(img_path).set_duration(duration_per_image)

            img_clip = img_clip.resize(height=1280)

            img_clip = img_clip.crop(
                x_center=img_clip.w / 2,
                y_center=img_clip.h / 2,
                width=720,
                height=1280
            )

            text = subtitles[i] if i < len(subtitles) else ""

            txt_clip = TextClip(
                text,
                fontsize=60,
                color="yellow",
                font="Liberation-Sans-Bold",
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(650, None)
            )

            txt_clip = txt_clip.set_position(("center", 1000)).set_duration(duration_per_image)

            final_scene = CompositeVideoClip([img_clip, txt_clip])

            video_clips.append(final_scene)

        final_video = concatenate_videoclips(video_clips)

        final_video = final_video.set_audio(audio_clip)

        os.makedirs("/tmp/ai_videos", exist_ok=True)

        output_path = f"/tmp/ai_videos/{job_id}.mp4"

        final_video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=1
        )

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["video_path"] = output_path

        print(f"✅ [{job_id}] Video Ready")

    except Exception as e:

        jobs[job_id]["status"] = "failed"

        print(f"❌ Error in merging {job_id}: {e}")


# ====================================================
# BASE64 REQUEST MODEL
# ====================================================

class Base64MergeRequest(BaseModel):

    audio_base64: str
    images_base64: List[str]
    subtitles: List[str]


# ====================================================
# BASE64 MERGE API
# ====================================================

@app.post("/merge-video-base64")

async def merge_video_base64(request: Base64MergeRequest, background_tasks: BackgroundTasks):

    job_id = str(uuid.uuid4())

    jobs[job_id] = {"status": "processing", "video_path": ""}

    work_dir = f"/tmp/work_{job_id}"

    os.makedirs(work_dir, exist_ok=True)

    try:

        audio_path = os.path.join(work_dir, "audio_input")

        audio_bytes = clean_base64_string(request.audio_base64)

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        saved_images = []

        for i, img_b64 in enumerate(request.images_base64):

            img_path = os.path.join(work_dir, f"scene_{i}.jpg")

            img_bytes = clean_base64_string(img_b64)

            with open(img_path, "wb") as f:
                f.write(img_bytes)

            saved_images.append(img_path)

        background_tasks.add_task(
            create_merged_video_task,
            job_id,
            saved_images,
            audio_path,
            request.subtitles
        )

        return {
            "job_id": job_id,
            "check_status_url": f"/check-video/{job_id}",
            "download_url": f"/download-video/{job_id}"
        }

    except Exception as e:

        jobs[job_id]["status"] = "failed"

        return {"error": str(e)}


# ====================================================
# FILE UPLOAD MERGE API
# ====================================================

@app.post("/merge-video")

async def merge_video(
        background_tasks: BackgroundTasks,
        audio: UploadFile = File(...),
        images: List[UploadFile] = File(...),
        subtitles_json: str = Form(...)
):

    job_id = str(uuid.uuid4())

    jobs[job_id] = {"status": "processing", "video_path": ""}

    work_dir = f"/tmp/work_{job_id}"

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

    subtitles = json.loads(subtitles_json)

    background_tasks.add_task(
        create_merged_video_task,
        job_id,
        saved_images,
        audio_path,
        subtitles
    )

    return {
        "job_id": job_id,
        "check_status_url": f"/check-video/{job_id}",
        "download_url": f"/download-video/{job_id}"
    }


# ====================================================
# CHECK STATUS
# ====================================================

@app.get("/check-video/{job_id}")

def check_video(job_id: str):

    if job_id not in jobs:
        return {"error": "Job not found"}

    return {"status": jobs[job_id]["status"]}


# ====================================================
# DOWNLOAD VIDEO
# ====================================================

@app.get("/download-video/{job_id}")

def download_video(job_id: str):

    if job_id not in jobs:
        return {"error": "Job not found"}

    if jobs[job_id]["status"] != "completed":
        return {"message": "Video still processing"}

    return FileResponse(
        jobs[job_id]["video_path"],
        media_type="video/mp4",
        filename=f"{job_id}.mp4"
    )


# ====================================================
# HOME
# ====================================================

@app.get("/")

def home():
    return {"status": "✅ AI Video Worker Running"}
