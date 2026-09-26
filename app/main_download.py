import threading
from pathlib import Path

from downloader import saturn_download
from download_queue import (
    append_to_file,
    delete_first_line_from_file,
    get_first_from_file,
)
from log_file import log_message

CONFIG_FILE = Path(".config")
stop_event = threading.Event()
download_thread = None

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
    
"""Start a worker, it will start one time, future calls will not start a new thread if the previous one is still running."""
def start_worker_thread(path=None, only_meta_data=False):
    global download_thread
    if download_thread is None or not download_thread.is_alive():
        log_message("Starting worker thread for downloading.")
        stop_event.clear()
        download_thread = threading.Thread(target=worker_download, args=(stop_event, path, only_meta_data))
        download_thread.start()
        log_message("Worker thread started.")
        
        
