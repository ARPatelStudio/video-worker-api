import os
import uuid
import base64
import subprocess
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip

from PIL import Image, ImageDraw, ImageFont

# Pillow compatibility fix (Pillow 10+)
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

app = FastAPI()

jobs = {}

# =========================
# Request Model
# =========================

class VideoRequest(BaseModel):
    images: list
    audio: str
    text: str


# =========================
# Home
# =========================

@app.get("/")
def home():
    return {"status": "AI Video Worker Running"}


# =========================
# Base64 Cleaner
# =========================

def clean_base64(data):

    if "," in data:
        data = data.split(",")[1]

    data += "=" * ((4 - len(data) % 4) % 4)

    return base64.b64decode(data)


# =========================
# Audio Fix
# =========================

def fix_audio(input_path):

    output = input_path + "_fixed.mp3"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "2",
        "-ar", "44100",
        output
    ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return output


# =========================
# Create Text Image
# =========================

def create_text_overlay(text, width=720, height=1280):

    img = Image.new("RGBA", (width, height), (0,0,0,0))

    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("LiberationSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0,0), text, font=font)

    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = (width - text_w) // 2
    y = height - text_h - 150

    draw.text((x,y), text, font=font, fill=(255,255,0,255))

    path = "/tmp/subtitle.png"

    img.save(path)

    return path


# =========================
# Video Processing
# =========================

def process_video(job_id, data):

    try:

        print(f"🎬 [{job_id}] Starting video merge")

        workspace = f"/tmp/work_{job_id}"

        os.makedirs(workspace, exist_ok=True)

        image_paths = []

        # Save Images
        for i, img_b64 in enumerate(data["images"]):

            img_path = f"{workspace}/img{i}.png"

            with open(img_path, "wb") as f:
                f.write(clean_base64(img_b64))

            image_paths.append(img_path)

        # Save Audio
        audio_path = f"{workspace}/audio_input"

        with open(audio_path, "wb") as f:
            f.write(clean_base64(data["audio"]))

        audio_path = fix_audio(audio_path)

        audio_clip = AudioFileClip(audio_path)

        duration = audio_clip.duration

        per_image = duration / len(image_paths)

        clips = []

        # Create Image Clips
        for img in image_paths:

            clip = ImageClip(img).set_duration(per_image)

            clip = clip.resize(height=1280)

            clip = clip.crop(
                x_center=clip.w/2,
                y_center=clip.h/2,
                width=720,
                height=1280
            )

            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose")

        video = video.set_audio(audio_clip)

        # Subtitle overlay
        subtitle_img = create_text_overlay(data["text"])

        txt_clip = (
            ImageClip(subtitle_img)
            .set_duration(video.duration)
            .set_position(("center","bottom"))
        )

        final = CompositeVideoClip([video, txt_clip])

        output = f"{workspace}/output.mp4"

        final.write_videofile(
            output,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=1
        )

        jobs[job_id] = {
            "status":"completed",
            "file":output
        }

        print(f"✅ [{job_id}] Video ready")

    except Exception as e:

        print(f"❌ Error {job_id}: {e}")

        jobs[job_id] = {
            "status":"failed",
            "error":str(e)
        }


# =========================
# Start Merge API
# =========================

@app.post("/merge-video")

def merge_video(req: VideoRequest):

    job_id = str(uuid.uuid4())

    jobs[job_id] = {"status":"processing"}

    threading.Thread(
        target=process_video,
        args=(job_id, req.dict())
    ).start()

    return {
        "job_id": job_id,
        "check_url": f"/check-video/{job_id}",
        "download_url": f"/download-video/{job_id}"
    }


# =========================
# Check Status
# =========================

@app.get("/check-video/{job_id}")

def check(job_id:str):

    if job_id not in jobs:
        return {"status":"not_found"}

    return jobs[job_id]


# =========================
# Download Video
# =========================

@app.get("/download-video/{job_id}")

def download(job_id:str):

    if job_id not in jobs:
        return {"error":"job not found"}

    if jobs[job_id]["status"] != "completed":
        return {"status":"processing"}

    return FileResponse(
        jobs[job_id]["file"],
        media_type="video/mp4",
        filename="video.mp4"
    )
