"""Common interface every site extractor has to implement.

An extractor knows ONE site and does only two things:

1. `extract_info()`            -> the metadata Jellyfin needs (title, plot, poster URL...)
2. `extract_download_link()`   -> the direct link of one item returned by `extract_items()`

An extractor never writes a file and never downloads anything: `jellyfin_writer.py`
writes the `.nfo` XML files, `downloader.py` does the actual download (and owns the
output path), and `main_download.py` glues the three together.
"""
from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """Site extractor contract."""

    url: str
    downloaded_info: dict | None
    d_info: bool
    header: dict

    def __init__(self, url: str = ""):
        self.set_all(url, None, False, {})

    def set_all(self, url: str, downloaded_info: dict | None, d_info: bool, header: dict):
        self.url = url
        self.downloaded_info = downloaded_info
        self.d_info = d_info
        self.header = header

    @abstractmethod
    def is_valid(self, url: str | None = None) -> bool:
        """True when this extractor knows how to handle `url` (defaults to the instance URL)."""

    @abstractmethod
    def extract_info(self) -> dict | None:
        """The metadata Jellyfin needs, or None when it cannot be extracted."""

    @abstractmethod
    def extract_items(self) -> list[dict]:
        """The items to download, each one a dict:

        {"title": str, "episode": int | None, "season": int | None,
         "page_url": str, "referer": str}
        """

    @abstractmethod
    def extract_download_link(self, item: dict) -> str | None:
        """The direct download link of one item returned by `extract_items()`."""
    