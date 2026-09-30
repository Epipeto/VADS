"""File downloader: the only module that writes media files to disk.

The extractors (`extractor/`) never touch the filesystem, they just return links.
Everything that needs a path lives here:

- `build_output_path()` creates the folder of a season inside the configured path;
- `download_video()` saves a resolved stream link with yt-dlp;
- `download_image()` saves the Jellyfin poster;
- `sanitize_filename()` turns a title into something usable as a file/folder name.
"""
import os
import re
from typing import Any, cast

import requests
import yt_dlp

from log_file import log_message

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Requests without a timeout can hang the worker thread forever.
REQUEST_TIMEOUT = 30


def sanitize_filename(name) -> str:
    """Make a string safe to use as a file/folder name."""
    if not name:
        return "unknown"
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", str(name))
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized or "unknown"


def build_output_path(base_path: str, folder_name: str) -> str:
    """Return (creating it if needed) the folder `folder_name` inside `base_path`."""
    target = os.path.join(base_path, folder_name) if base_path else folder_name
    os.makedirs(target, exist_ok=True)
    log_message(f"Download path set to: {target}")
    return target


def download_video(url: str, path: str, title: str | None = None, referer: str | None = None, headers: dict | None = None) -> bool:
    """Download `url` into `path` with yt-dlp, naming the file after `title`."""
    os.makedirs(path, exist_ok=True)

    request_headers = dict(headers or {})
    request_headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    if referer:
        request_headers.setdefault("Referer", referer)

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "paths": {"home": path},
        "outtmpl": f"{title}.%(ext)s" if title else "%(title)s.%(ext)s",
        "http_headers": request_headers,
    }

    log_message(f"Downloading video. Path: {path}, Title: {title}")
    try:
        with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
            ydl.download([url])
    except Exception as e:
        log_message(f"An error occurred while downloading {url}: {e}")
        return False

    log_message(f"Video downloaded: {title or url}")
    return True


def download_image(url: str, path: str, filename: str = "poster.jpg", headers: dict | None = None) -> bool:
    """Download an image (the Jellyfin poster) as `path/filename`."""
    request_headers = dict(headers or {})
    request_headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

    try:
        response = requests.get(url, headers=request_headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        log_message(f"Failed to download image {url}: {e}")
        return False

    os.makedirs(path, exist_ok=True)
    target_path = os.path.join(path, filename)
    with open(target_path, "wb") as image_file:
        image_file.write(response.content)
    log_message(f"Saved image: {target_path}")
    return True
