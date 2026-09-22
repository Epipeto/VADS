"""File-based FIFO download queue shared by every download site.

The queue is a plain text file (`download_queue.queue`) with one URL per line.
The first line is the entry currently being processed: the worker removes it
only after the download finished, so the UI can show it as "in corso".
Extra sites just append their own URLs, so the queue stays site-agnostic.

NOTE: this module is deliberately not named `queue.py`. A top-level `queue.py`
inside `app/` would shadow the Python standard library `queue` module (urllib3,
hence requests, imports it) and break the whole backend.

Every read/write goes through a lock because the Flask request thread and the
download worker thread both touch the file.
"""
import threading
from pathlib import Path

QUEUE_FILE = Path("download_queue.queue")
file_lock = threading.Lock()


def _read_queue():
    """Return the queued URLs, stripped, ignoring blank lines."""
    if not QUEUE_FILE.is_file():
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def append_to_file(url):
    """Append a URL at the end of the queue (FIFO: it gets processed last)."""
    url = (url or "").strip()
    if not url:
        return
    with file_lock:
        with open(QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")


def get_first_from_file():
    """Return the first queued URL without removing it (None when empty)."""
    with file_lock:
        lines = _read_queue()
        return lines[0] if lines else None


def delete_first_line_from_file():
    """Remove the first URL, marking it as finished."""
    with file_lock:
        remaining_lines = _read_queue()[1:]
        # Rewrite the file keeping only the remaining entries.
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            for line in remaining_lines:
                f.write(f"{line}\n")


def count_url_file():
    """Number of queued URLs."""
    with file_lock:
        return len(_read_queue())


def get_all_from_file():
    """All queued URLs: index 0 is the one currently being downloaded."""
    with file_lock:
        return _read_queue()


def is_queue_empty():
    """True when there is nothing left to process."""
    return count_url_file() == 0
