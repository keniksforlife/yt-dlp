from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
import yt_dlp
from typing import Optional
import os
import uuid
import re
from datetime import datetime
from pathlib import Path

app = FastAPI(title="yt-dlp API")

# Configuration
COOKIES_FILE = "cookies.txt"
DOWNLOADS_DIR = "downloads"

def verify_cookies():
    """Verify if cookies file exists and is readable"""
    cookies_path = Path(COOKIES_FILE)
    if not cookies_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Cookies file not found. Please configure cookies.txt"
        )
    if not os.access(cookies_path, os.R_OK):
        raise HTTPException(
            status_code=500,
            detail="Cookies file is not readable. Please check permissions"
        )
    return str(cookies_path.absolute())

def create_safe_filename(title: str) -> str:
    # Remove special characters and spaces
    safe_title = re.sub(r'[^\w\s-]', '', title)
    safe_title = re.sub(r'\s+', '-', safe_title)
    
    # Create unique filename with timestamp and UUID
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4())[:8]
    
    return f"{timestamp}_{safe_title}_{unique_id}"

def get_yt_dlp_options(base_filename: str, format: str, quality: str) -> dict:
    """Create yt-dlp options with proper cookie handling"""
    cookies_path = verify_cookies()
    
    return {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOADS_DIR}/{base_filename}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractaudio': True,
        'audioformat': format,
        'audioquality': quality,
        'cookiesfile': cookies_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': format,
            'preferredquality': quality,
        }],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    }

@app.post("/download/audio")
async def download_audio(
    url: str,
    format: str = Query("mp3", description="Audio format (mp3, m4a, wav, etc)"),
    quality: str = Query("192", description="Audio quality in kbps")
):
    try:
        # Ensure downloads directory exists
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        
        # First try to get video info
        options = get_yt_dlp_options("", format, quality)
        with yt_dlp.YoutubeDL({'quiet': True, 'cookiesfile': options['cookiesfile']}) as ydl:
            info = ydl.extract_info(url, download=False)
            base_filename = create_safe_filename(info["title"])
            final_filename = f"{base_filename}.{format}"
            
        # Update options with the filename
        options = get_yt_dlp_options(base_filename, format, quality)
        
        # Perform download
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = os.path.join(DOWNLOADS_DIR, final_filename)
            
            # Handle potential double extension
            if not os.path.exists(file_path):
                double_ext_path = os.path.join(DOWNLOADS_DIR, f"{final_filename}.{format}")
                if os.path.exists(double_ext_path):
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
    except yt_dlp.utils.DownloadError as e:
        if "Sign in to confirm your age" in str(e):
            raise HTTPException(
                status_code=400,
                detail="Age-restricted video. Please check your cookies configuration."
            )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/info")
async def get_video_info(url: str):
    try:
        options = {'quiet': True, 'cookiesfile': verify_cookies()}
        with yt_dlp.YoutubeDL(options) as ydl:
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
