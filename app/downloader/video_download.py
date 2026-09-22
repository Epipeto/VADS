import yt_dlp
import requests
from bs4 import BeautifulSoup
import re
import base64
from typing import Any, cast
from urllib.parse import urlparse, parse_qs

from log_file import log_message


def xor_decode(b64_data, key):
    """Decode the embed player's base64+XOR obfuscated string (dec() in embed page JS)."""
    log_message(f"Decoding base64+XOR data with key: {key}")
    if not b64_data:
        return ''
    raw = base64.b64decode(b64_data)
    return bytes(c ^ ord(key[i % len(key)]) for i, c in enumerate(raw)).decode('utf-8', errors='replace')


def extract_source_from_embed(embed_url, headers):
    """Call the embed player's /playlist endpoint and decode the real video URL."""
    
    parsed = urlparse(embed_url)
    qs = parse_qs(parsed.query)
    token = qs.get('token', [None])[0]
    expires = qs.get('expires', [None])[0]
    if not token or not expires:
        return None
    
    log_message(f"Extracting source from embed URL: {embed_url} with token: {token} and expires: {expires}")
    playlist_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}/playlist?token={token}&expires={expires}"
    playlist_headers = headers.copy()
    playlist_headers['Referer'] = embed_url

    resp = requests.get(playlist_url, headers=playlist_headers)
    if resp.status_code != 200:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    return xor_decode(data.get('d'), token)


def download_animesaturn_video(url, path=None, title=None):
    log_message(f"Starting download for video URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',    
        'Referer': url
    }
    response = requests.get(url, headers=headers)
    
    if (response.status_code != 200):
        log_message(f"Failed to fetch the page. Status code: {response.status_code}")
        return
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    #iframe location
    embed_url = None
    
    log_message("Searching for the iframe that contains the video.")
    # Find the iframe that contains the video
    for iframe in soup.find_all('iframe'):
        src = str(iframe.get('src') or '')
        if src and ('stream' in src or 'embed' in src or 'watch' in src):
            embed_url = src
            break
    
    log_message(f"Found embed URL: {embed_url}" if embed_url else "No suitable iframe found for video.")
    # If the embed URL is not found in iframes, try to find it in the page's JavaScript
    if not embed_url:
        matches = re.findall(r'https?://[^\s\'"]+\.(?:mp4|m3u8)[^\s\'"]*', response.text)
        if matches:
            embed_url = matches[0]
    if not embed_url:
        log_message("Could not automatically find the video URL. Please provide the direct video URL.")
        return    
    
    embed_headers = headers.copy()
    embed_headers['Referer'] = url
    
    log_message(f"Attempting to extract the direct stream URL from the embed URL: {embed_url}")
    direct_stream_url = extract_source_from_embed(embed_url, embed_headers)

    log_message(f"Direct stream URL extracted: {direct_stream_url}" if direct_stream_url else "Could not extract direct stream URL from embed.")
    if not direct_stream_url:
        log_message("Attempting to find the video source URL directly from the embed page.")
        embed_response = requests.get(embed_url, headers=embed_headers)
        # Add this right after getting embed_response:
        video_sources = re.findall(r'https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*', embed_response.text)

        # If the video source is not found, try to extract it from the embed page's JavaScript    
        if not video_sources:
            video_sources = re.findall(r'file\s*:\s*["\']([^"\']+)["\']', embed_response.text)

        if not video_sources:
            log_message("Could not find the video source URL. Please provide the direct video URL.")
            return
        log_message(f"Found video sources: {video_sources}")
        direct_stream_url = video_sources[0]

    
    # Set up yt-dlp options
    log_message(f"Setting up yt-dlp options for downloading. Path: {path}, Title: {title}")
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "paths": {"home": path if path else "."},
        "outtmpl": f"{title}.%(ext)s" if title else "%(title)s.%(ext)s",
        "http_headers": {
            "User-Agent": headers["User-Agent"],
            "Referer": embed_url,
        },
    }
    log_message(f"Starting download with yt-dlp for URL: {direct_stream_url}")
    try:
        with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
            ydl.download([direct_stream_url])    
    except Exception as e:
        log_message(f"An error occurred: {e}")
        
    