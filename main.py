import os
import uuid
import shutil
import subprocess
import threading
import traceback
import textwrap
from typing import List

from fastapi import FastAPI, Form, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests

from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip
import moviepy.video.fx.all as vfx

from PIL import Image, ImageDraw, ImageFont

# =========================
# Pillow compatibility fix
# =========================
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

app = FastAPI()
jobs = {}

@app.get("/")
def home():
    return {"status": "✅ AI Video Worker Running with Cloud Whisper (Groq)!"}

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
# Groq API Whisper (Zero RAM usage on Render)
# =========================
def get_word_timestamps_from_groq(audio_path):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise Exception("❌ GROQ_API_KEY is missing in Render Environment Variables!")
        
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    with open(audio_path, "rb") as f:
        files = {
            "file": (os.path.basename(audio_path), f, "audio/wav")
        }
        data = {
            "model": "whisper-large-v3",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word"
        }
        print("☁️ Sending audio to Groq Cloud for transcription...")
        response = requests.post(url, headers=headers, files=files, data=data)
        
    if response.status_code != 200:
        raise Exception(f"Groq API Error: {response.text}")
        
    result = response.json()
    return result.get("words", [])

# =========================
# 2026 MODERN WORD-BY-WORD CAPTIONS
# =========================
def create_word_overlay(word, width=720, height=1280):
    img = Image.new("RGBA", (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("LiberationSans-Bold.ttf", 85)
    except:
        font = ImageFont.load_default()

    word = word.strip().upper()
    bbox = draw.textbbox((0,0), word, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x_start = (width - text_w) // 2
    y_start = int(height * 0.70) 
    
    box_padding = 20
    draw.rectangle(
        [x_start - box_padding, y_start - box_padding, x_start + text_w + box_padding, y_start + text_h + box_padding],
        fill=(0, 0, 0, 200)
    )
    
    draw.text(
        (x_start, y_start), word, font=font, fill=(255, 230, 0, 255), 
        stroke_width=5, stroke_fill=(0, 0, 0, 255)
    )
        
    path = f"/tmp/word_{uuid.uuid4().hex}.png"
    img.save(path)
    return path

# =========================
# ADVANCED VIDEO PROCESSING
# =========================
def process_video(job_id, image_paths, audio_path, text):
    try:
        print(f"🎬 [{job_id}] Starting Advanced Video Merge")
        workspace = f"/tmp/work_{job_id}"
        
        audio_path = fix_audio(audio_path)
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration
        per_image = duration / max(1, len(image_paths))
        clips = []

        for i, img in enumerate(image_paths):
            clip = ImageClip(img).set_duration(per_image)
            clip = clip.resize(height=1400) 
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)

            if i % 2 == 0:
                clip = clip.resize(lambda t: 1 + 0.04 * (t / per_image)) 
            else:
                clip = clip.resize(lambda t: 1.04 - 0.04 * (t / per_image)) 
            
            clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=720, height=1280)
            clip = clip.fx(vfx.colorx, 1.05) 
            clip = clip.fadein(0.3).fadeout(0.3)
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio_clip)

        # Get Words from Groq API
        words_data = get_word_timestamps_from_groq(audio_path)
        
        subtitle_clips = []
        for word_info in words_data:
            word_text = word_info['word']
            start_time = word_info['start']
            end_time = word_info['end']
            
            word_img_path = create_word_overlay(word_text)
            txt_clip = (ImageClip(word_img_path)
                        .set_start(start_time)
                        .set_end(end_time)
                        .set_position(("center", "center")))
            subtitle_clips.append(txt_clip)

        if subtitle_clips:
            print(f"✍️ [{job_id}] Applying {len(subtitle_clips)} Word Captions from Groq...")
            final = CompositeVideoClip([video] + subtitle_clips)
        else:
            final = video

        output = f"{workspace}/output.mp4"

        print(f"🚀 [{job_id}] Rendering Final MP4...")
        final.write_videofile(
            output, fps=24, codec="libx264", audio_codec="aac", 
            preset="ultrafast", threads=1
        )

        jobs[job_id] = {"status":"completed", "file":output}
        print(f"✅ [{job_id}] Video ready with Word-by-Word Effects!")

    except Exception as e:
        print(f"❌ Error {job_id}: {e}")
        traceback.print_exc()
        jobs[job_id] = {"status":"failed", "error":str(e)}

@app.post("/merge-video")
def merge_video_file(
    audio: UploadFile = File(...),
    images: List[UploadFile] = File(...),
    text: str = Form(...) 
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status":"processing"}
    workspace = f"/tmp/work_{job_id}"
    os.makedirs(workspace, exist_ok=True)

    audio_path = os.path.join(workspace, audio.filename)
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    saved_images = []
    for i, img in enumerate(images):
        img_path = os.path.join(workspace, f"img_{i}.png")
        with open(img_path, "wb") as f:
            shutil.copyfileobj(img.file, f)
        saved_images.append(img_path)

    threading.Thread(target=process_video, args=(job_id, saved_images, audio_path, text)).start()

    return {"job_id": job_id, "check_url": f"/check-video/{job_id}", "download_url": f"/download-video/{job_id}"}

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
