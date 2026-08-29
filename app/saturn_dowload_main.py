import threading
from pathlib import Path
from season_download import download_animesaturn_season
from log_file import log_message

QUEUE_FILE = Path("download_queue.queue")
CONFIG_FILE = Path(".config")
file_lock = threading.Lock()
stop_event = threading.Event()
download_thread = None

"""append a URL to the queue file."""
def appen_to_file(url):
    with file_lock:
        with open(QUEUE_FILE, "a") as f:
            f.write(url + "\n")
            
def get_first_from_file():
    """Estrae il PRIMO URL dal file senza rimuoverlo (FIFO)."""
    with file_lock:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        
        if not lines:
            return None
        
        first_url = lines[0]
        return first_url
def delete_first_line_from_file():
    """Rimuove il PRIMO URL dal file (FIFO)."""
    with file_lock:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        
        if not lines:
            return
        
        remaining_lines = lines[1:]
        
        # Sovrascrive il file mantenendo solo gli elementi rimanenti
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            for line in remaining_lines:
                f.write(f"{line}\n")

def count_url_file():
    with file_lock:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return len(lines)

def get_all_from_file():
    """Ritorna tutti gli URL presenti in coda (FIFO, il primo e' quello in download)."""
    with file_lock:
        if not QUEUE_FILE.is_file():
            return []
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

def is_worker_running():
    return download_thread is not None and download_thread.is_alive()

def get_config_path():
    if not CONFIG_FILE.is_file():
        return ""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return f.readline().strip().split("=")[-1].strip()

def set_config_path(path):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(f"path={path}\n")

"""Start a worker, it will start one time, future calls will not start a new thread if the previous one is still running."""
def start_worker_thread(path=None):
    global download_thread
    if download_thread is None or not download_thread.is_alive():
        log_message("Starting worker thread for downloading.")
        stop_event.clear()
        download_thread = threading.Thread(target=worker_download, args=(stop_event, path))
        download_thread.start()
        log_message("Worker thread started.")
        
def worker_download(stop_event, path=None):
    while not stop_event.is_set():
        # get the first URL from the queue file
        url = get_first_from_file()
        log_message(f"Worker thread processing URL: {url}")
        if url:
            try:
                log_message(f"Starting download for URL: {url}")
                download_animesaturn_season(url, path=path)
                log_message(f"Finished download for URL: {url}")
                
                delete_first_line_from_file()
            except Exception as e:
                log_message(f"Error downloading {url}: {e}")
            
        else:
            break

    
def saturn_download_main(url):
    log_message(f"Try to add url: {url}")
    
    if not ("anime" in url or "hentai" in url) or "ep" in url:
        log_message("Invalid URL provided. Please provide a valid anime or hentai season URL.")
        return
    if not CONFIG_FILE.is_file():
        log_message(f"Configuration file '{CONFIG_FILE}' not found. Please create it with the download path.")
        return
    
    path = get_config_path()
    appen_to_file(url)
    log_message(f"URL added to queue: {url}")
    start_worker_thread(path=path)



