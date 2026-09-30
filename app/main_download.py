"""Generic download orchestrator.

This module is site agnostic: for every URL it

1. picks the extractor that recognizes the link (`extractor/`),
2. asks it for the Jellyfin metadata -> written by `jellyfin_writer.py`,
3. asks it for the download links -> downloaded by `downloader.py`.

Adding a new site only means adding the extractor to `EXTRACTORS`.
"""
import threading
from pathlib import Path

import downloader
import jellyfin_writer
from download_queue import (
    append_to_file,
    delete_first_line_from_file,
    get_first_from_file,
)
from extractor.missav_downloader import MissavDownloader
from extractor.saturn_download import AnimeSaturnDownloader
from log_file import log_message

CONFIG_FILE = Path(".config")
stop_event = threading.Event()
download_thread = None

# Tried in order: the first extractor whose `is_valid()` accepts the URL wins.
EXTRACTORS = (AnimeSaturnDownloader, MissavDownloader)


def is_worker_running():
    return download_thread is not None and download_thread.is_alive()


def _read_config():
    """Reads the config file into a {key: value} dict. Returns {} if absent."""
    config = {}
    if CONFIG_FILE.is_file():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()
    return config


def _write_config(config):
    """Rewrites the whole config file keeping the path/meta_data keys."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(f"path={config.get('path', '')}\n")
        f.write(f"meta_data={config.get('meta_data', '0')}\n")


def get_config_path():
    if not CONFIG_FILE.is_file():
        return ""
    return _read_config().get("path", "")


def set_config_path(path):
    config = _read_config()
    config["path"] = path
    _write_config(config)


def get_config_meta_data():
    if not CONFIG_FILE.is_file():
        return False
    config = _read_config()
    # "onlymetadata" is accepted as a legacy alias for "meta_data".
    value = config.get("meta_data", config.get("onlymetadata", "0"))
    return value == "1"


def set_config_metadata(enabled):
    """Saves the 'only metadata' flag: True => only NFO/images are downloaded (no videos)."""
    config = _read_config()
    config["meta_data"] = "1" if enabled else "0"
    _write_config(config)


def pick_extractor(url: str):
    """The extractor that handles `url` (based on the link), or None."""
    if not url:
        return None
    for extractor_cls in EXTRACTORS:
        extractor = extractor_cls(url)
        if extractor.is_valid():
            return extractor
    return None


def download_url(url: str, path: str | None = None, only_meta_data: bool = False):
    """Download `url` into `path` (or write only its metadata when asked to)."""
    extractor = pick_extractor(url)
    if extractor is None:
        log_message(f"No downloader found for URL: {url}")
        return
    log_message(f"Using {type(extractor).__name__} for URL: {url}")

    info = extractor.extract_info()
    if not info:
        log_message(f"Failed to extract the metadata of: {url}")
        return

    items = extractor.extract_items()
    if not items:
        log_message(f"No downloadable items found for: {url}")
        return

    if not path:
        path = get_config_path()
    if not path:
        log_message("No download path configured, please set it in the settings.")
        return

    # The downloader owns the path: it creates the season folder for us.
    season_path = downloader.build_output_path(path, downloader.sanitize_filename(info.get("title")))

    # Jellyfin metadata: the season NFO and the poster.
    jellyfin_writer.write_tvshow_nfo(season_path, info)
    if info.get("anime_poster"):
        downloader.download_image(info["anime_poster"], season_path, "poster.jpg", headers=extractor.header)

    for index, item in enumerate(items, start=1):
        title = item.get("title") or f"Episode {index}"
        # The video file and its .nfo must share the same base name.
        safe_title = downloader.sanitize_filename(title)
        jellyfin_writer.write_episode_nfo(
            season_path,
            safe_title,
            title,
            item.get("episode") or index,
            item.get("season") or 1,
        )

        if only_meta_data:
            continue

        log_message(f"Starting download of {title}.")
        stream_url = extractor.extract_download_link(item)
        if not stream_url:
            log_message(f"Could not extract the download link of: {title}")
            continue
        downloader.download_video(
            stream_url,
            season_path,
            title=safe_title,
            referer=item.get("referer") or url,
        )
        log_message(f"Finished downloading {title}.")

    if only_meta_data:
        log_message("Only metadata downloaded, skipping the videos as per configuration.")


def worker_download(stop_event, path=None, only_meta_data=False):
    """Process the queue one URL at a time until it is empty (or stopped)."""
    while not stop_event.is_set():
        url = get_first_from_file()
        if not url:
            break

        log_message(f"Worker thread processing URL: {url}")
        try:
            download_url(url, path=path, only_meta_data=only_meta_data)
            log_message(f"Finished download for URL: {url}")
        except Exception as e:
            log_message(f"Error downloading {url}: {e}")
        finally:
            # Drop the entry even on failure, otherwise the loop retries it forever.
            delete_first_line_from_file()


def start_worker_thread(path=None, only_meta_data=False):
    """Start a worker; repeated calls do nothing while the previous one still runs."""
    global download_thread
    if download_thread is None or not download_thread.is_alive():
        log_message("Starting worker thread for downloading.")
        stop_event.clear()
        download_thread = threading.Thread(target=worker_download, args=(stop_event, path, only_meta_data))
        download_thread.start()
        log_message("Worker thread started.")


def download_main(url: str):
    """API entry point: queue `url` and make sure a worker is running."""
    url = (url or "").strip()
    if not url:
        log_message("No URL provided.")
        return
    if pick_extractor(url) is None:
        log_message(f"Invalid URL provided, no downloader handles it: {url}")
        return
    if not CONFIG_FILE.is_file():
        log_message(f"Configuration file '{CONFIG_FILE}' not found. Please create it with the download path.")
        return

    append_to_file(url)
    log_message(f"URL added to queue: {url}")
    start_worker_thread(path=get_config_path(), only_meta_data=get_config_meta_data())
