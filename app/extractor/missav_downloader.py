"""MissAV extractor.

Placeholder: the class is already wired into `main_download.EXTRACTORS`, so
missav.com URLs are routed here, but the scraping itself is not written yet.
"""
from log_file import log_message

from .baseClass import BaseExtractor


class MissavDownloader(BaseExtractor):
    """Extractor for missav.com (not implemented yet)."""

    def is_valid(self, url: str | None = None) -> bool:
        target = url if url is not None else self.url
        return bool(target) and "missav" in target

    def extract_info(self) -> dict | None:
        log_message("Missav support is not implemented yet.")
        return None

    def extract_items(self) -> list[dict]:
        log_message("Missav support is not implemented yet.")
        return []

    def extract_download_link(self, item: dict) -> str | None:
        log_message("Missav support is not implemented yet.")
        return None
    