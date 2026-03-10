import base64
import uuid
import os
import threading

from fastapi import FastAPI
from pydantic import BaseModel

from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont

app = FastAPI()

jobs = {}

class VideoRequest(BaseModel):
    images: list
    audio: str
    text: str


@app.get("/")
def home():
    return {"status": "Video Worker Running"}


def create_text_image(text, width=1280, height=720):

    img = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("LiberationSans-Regular.ttf", 60)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0,0), text, font=font)

    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pos = ((width-text_w)//2,(height-text_h)//2)

    draw.text(pos, text, font=font, fill=(255,255,255))

    path = "/tmp/text.png"
    img.save(path)

    return path


def merge_video(job_id,data):

    try:

        print(f"🎬 [{job_id}] Video merging started")

        workspace = f"/tmp/workspace_{job_id}"
        os.makedirs(workspace,exist_ok=True)

        image_paths=[]

        for i,img_b64 in enumerate(data["images"]):

            path=f"{workspace}/img{i}.png"

            with open(path,"wb") as f:
                f.write(base64.b64decode(img_b64))

            image_paths.append(path)

        audio_path=f"{workspace}/audio.mp3"

        with open(audio_path,"wb") as f:
            f.write(base64.b64decode(data["audio"]))


        clips=[]

        for img in image_paths:

            clip=ImageClip(img).set_duration(2)
            clips.append(clip)

        video=concatenate_videoclips(clips,method="compose")

        audio=AudioFileClip(audio_path)

        video=video.set_audio(audio)

        text_img=create_text_image(data["text"])

        txt_clip=(ImageClip(text_img)
                  .set_duration(video.duration)
                  .set_pos("center"))

        final=CompositeVideoClip([video,txt_clip])

        output=f"{workspace}/output.mp4"

        final.write_videofile(output,fps=24)

        jobs[job_id]={"status":"done","file":output}

        print(f"✅ [{job_id}] Video ready")

    except Exception as e:

        print(f"❌ Error in merging {job_id}: {e}")

        jobs[job_id]={"status":"error","error":str(e)}



@app.post("/merge-video")
def merge_video_api(req:VideoRequest):

    job_id=str(uuid.uuid4())

    jobs[job_id]={"status":"processing"}

    threading.Thread(
        target=merge_video,
        args=(job_id,req.dict())
    ).start()

    return {"job_id":job_id}



@app.get("/check-video/{job_id}")
def check_video(job_id:str):

    return jobs.get(job_id,{"status":"not_found"})
