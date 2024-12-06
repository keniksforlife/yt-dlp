from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
import yt_dlp
from typing import Optional
import os
import uuid
import re
from datetime import datetime

app = FastAPI(title="yt-dlp API")

def create_safe_filename(title: str) -> str:
    # Remove special characters and spaces
    safe_title = re.sub(r'[^\w\s-]', '', title)
    safe_title = re.sub(r'\s+', '-', safe_title)
    
    # Create unique filename with timestamp and UUID
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4())[:8]
    
    return f"{timestamp}_{safe_title}_{unique_id}"

@app.post("/download/audio")
async def download_audio(
    url: str,
    format: str = Query("mp3", description="Audio format (mp3, m4a, wav, etc)"),
    quality: str = Query("192", description="Audio quality in kbps")
):
    try:
        # Generate base filename without extension
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            base_filename = create_safe_filename(info["title"])
            final_filename = f"{base_filename}.{format}"
            
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'downloads/{base_filename}.%(ext)s',  # Let yt-dlp handle extension
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'extractaudio': True,
            'audioformat': format,
            'audioquality': quality,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format,
                'preferredquality': quality,
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = os.path.join('downloads', final_filename)
            
            # Check if file exists with potential double extension
            if not os.path.exists(file_path):
                double_ext_path = os.path.join('downloads', f"{final_filename}.{format}")
                if os.path.exists(double_ext_path):
                    # Rename file to remove double extension
                    os.rename(double_ext_path, file_path)
            
            return {
                "status": "success",
                "title": info["title"],
                "duration": info.get("duration"),
                "filename": final_filename,
                "format": format,
                "quality": quality,
                "download_url": f"/download/{final_filename}"
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download/{filename}")
async def get_file(filename: str):
    # Try different possible file paths
    possible_paths = [
        os.path.join("downloads", filename),
        os.path.join("downloads", f"{filename}.{filename.split('.')[-1]}"),
        os.path.join("downloads", filename.replace('.mp3.mp3', '.mp3'))
    ]
    
    for file_path in possible_paths:
        if os.path.exists(file_path):
            return FileResponse(
                path=file_path,
                filename=filename.replace('.mp3.mp3', '.mp3'),
                media_type='audio/mpeg'
            )
    
    raise HTTPException(status_code=404, detail=f"File not found. Tried paths: {possible_paths}")

@app.get("/downloads")
async def list_downloads():
    downloads_dir = "downloads"
    if not os.path.exists(downloads_dir):
        return {"files": []}
    
    files = []
    for filename in os.listdir(downloads_dir):
        file_path = os.path.join(downloads_dir, filename)
        files.append({
            "filename": filename,
            "size": os.path.getsize(file_path),
            "download_url": f"/download/{filename}"
        })
    
    return {"files": files}


@app.get("/info")
async def get_video_info(url: str):
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info["title"],
                "duration": info.get("duration"),
                "description": info.get("description"),
                "thumbnail": info.get("thumbnail"),
                "formats": [
                    {
                        "format_id": f["format_id"],
                        "ext": f["ext"],
                        "resolution": f.get("resolution", "N/A"),
                        "filesize": f.get("filesize", "N/A"),
                        "acodec": f.get("acodec", "N/A"),
                        "vcodec": f.get("vcodec", "N/A"),
                    }
                    for f in info["formats"]
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
