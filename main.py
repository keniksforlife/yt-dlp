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
DOWNLOADS_DIR = os.getenv('DOWNLOADS_DIR', '/tmp/downloads')
COOKIES_CONTENT = os.getenv('YOUTUBE_COOKIES')

def verify_cookies():
    """Verify if cookies are configured"""
    if not COOKIES_CONTENT:
        raise HTTPException(
            status_code=500,
            detail="YouTube cookies not configured. Please set YOUTUBE_COOKIES environment variable."
        )
    return COOKIES_CONTENT

def create_safe_filename(title: str) -> str:
    # Remove special characters and spaces
    safe_title = re.sub(r'[^\w\s-]', '', title)
    safe_title = re.sub(r'\s+', '-', safe_title)
    
    # Create unique filename with timestamp and UUID
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4())[:8]
    
    return f"{timestamp}_{safe_title}_{unique_id}"

def get_yt_dlp_options(base_filename: str, format: str, quality: str) -> dict:
    """Create yt-dlp options with cookies from environment"""
    verify_cookies()  # Ensure cookies are configured
    
    return {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOADS_DIR}/{base_filename}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractaudio': True,
        'audioformat': format,
        'audioquality': quality,
        'cookies': COOKIES_CONTENT,  # Pass cookies content directly
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
        with yt_dlp.YoutubeDL(options) as ydl:
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

@app.get("/download/{filename}")
async def get_file(filename: str):
    possible_paths = [
        os.path.join(DOWNLOADS_DIR, filename),
        os.path.join(DOWNLOADS_DIR, f"{filename}.{filename.split('.')[-1]}"),
        os.path.join(DOWNLOADS_DIR, filename.replace('.mp3.mp3', '.mp3'))
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
    if not os.path.exists(DOWNLOADS_DIR):
        return {"files": []}
    
    files = []
    for filename in os.listdir(DOWNLOADS_DIR):
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        files.append({
            "filename": filename,
            "size": os.path.getsize(file_path),
            "download_url": f"/download/{filename}"
        })
    
    return {"files": files}

@app.get("/info")
async def get_video_info(url: str):
    try:
        options = get_yt_dlp_options("", "mp3", "192")  # Default format and quality for info
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

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cookies_configured": bool(COOKIES_CONTENT),
        "downloads_dir": DOWNLOADS_DIR
    }