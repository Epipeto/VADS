"""AnimeSaturn / HentaiSaturn downloader.

Self-contained implementation: it merges what used to live in
`season_download.py` (season scraping + Jellyfin NFO/images) and
`video_download.py` (player embed resolution + yt-dlp download).

It subclasses `Downloader`, so a generic orchestrator can pick it just by
asking the class itself whether it handles a URL:

    for downloader_cls in DOWNLOADERS:        # (AnimeSaturnDownloader, ...)
        downloader = downloader_cls(url, path=path, only_meta_data=flag)
        if downloader.is_valid():
            downloader.download()
            break

Everything a caller normally needs is `is_valid()`, `extract_info()` and
`download()`; the rest are implementation helpers.
"""

import base64
import os
import re
from typing import Any, cast
from urllib.parse import parse_qs, urljoin, urlparse
from xml.sax.saxutils import escape

import requests
import yt_dlp
from bs4 import BeautifulSoup

from log_file import log_message

from .baseClass import Downloader

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Requests without a timeout can hang the worker thread forever.
REQUEST_TIMEOUT = 30

# Episode pages end with `/ep-12`: both `/episode/<slug>/ep-12` (landing page)
# and `/hentai/<slug>/ep-12` (page with the player) match. A plain substring
# check on "ep" would also match half of the anime slugs, hence the regex.
EPISODE_URL_RE = re.compile(r"/ep-?\d+(?:[/?#]|$)", re.IGNORECASE)


def _find(node, *args, **kwargs):
    """`find` that tolerates a missing parent (returns None instead of raising)."""
    return node.find(*args, **kwargs) if node is not None else None


def _text(node) -> str | None:
    """Stripped text of a tag, or None when the tag is missing."""
    return node.get_text(strip=True) if node is not None else None


class AnimeSaturnDownloader(Downloader):
    """Downloader for AnimeSaturn/HentaiSaturn seasons and single episodes."""

    def __init__(self, url: str, path: str = "", only_meta_data: bool = False):
        self.set_all(url, {}, False, self._build_headers(url), path)
        self.only_meta_data = only_meta_data

    # ------------------------------------------------------------------ API

    def is_valid(self, url: str | None = None) -> bool:
        """True for AnimeSaturn/HentaiSaturn URLs; defaults to the instance URL."""
        target = url if url is not None else self.url
        if not target:
            return False
        return "animesaturn" in target or "hentaisaturn" in target

    @staticmethod
    def is_episode_url(url: str) -> bool:
        """True when the URL points to a single episode instead of a season."""
        return bool(EPISODE_URL_RE.search(url or ""))

    def extract_info(self) -> dict | None:
        """Fetch the page and return its metadata, caching it in `downloaded_info`.

        Returns None when the info was already extracted (`d_info`) or when the
        page cannot be fetched/parsed.
        """
        if self.d_info:
            return None

        soup = self._fetch_soup(self.url)
        if soup is None:
            return None

        generic_info = self._extract_generic_info(soup)
        if not generic_info:
            log_message("Failed to extract information about the season.")
            return None

        # Cache the result: a second call returns None instead of re-fetching.
        self.downloaded_info = generic_info
        self.d_info = True
        return generic_info

    def download(self):
        """Download the single episode or the whole season this instance points at."""
        if self.is_episode_url(self.url):
            self._download_video(self.url, self.path)
        else:
            self._download_season(self.url, self.path)

    @staticmethod
    def sanitize_filename(name) -> str:
        """Make a string safe to use as a file/folder name."""
        if not name:
            return "unknown"
        sanitized = re.sub(r'[\\/:*?"<>|]+', "_", str(name))
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized or "unknown"

    # ------------------------------------------------------- HTTP utilities

    @staticmethod
    def _build_headers(url: str, referer: str | None = None) -> dict:
        """Browser headers for `url`; the referer defaults to the URL itself."""
        return {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": referer or url,
        }

    @staticmethod
    def _fetch_text(url: str, referer: str | None = None) -> str | None:
        """GET a page and return its HTML; None on network/HTTP errors."""
        log_message(f"Fetching page: {url}")
        try:
            response = requests.get(
                url,
                headers=AnimeSaturnDownloader._build_headers(url, referer),
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            log_message(f"Failed to fetch the page {url}: {e}")
            return None

        if response.status_code != 200:
            log_message(f"Failed to fetch the page {url}. Status code: {response.status_code}")
            return None

        return response.text

    def _fetch_soup(self, url: str, referer: str | None = None) -> BeautifulSoup | None:
        """Like `_fetch_text`, but parsed with BeautifulSoup."""
        text = self._fetch_text(url, referer)
        return BeautifulSoup(text, "html.parser") if text is not None else None

    # --------------------------------------------------------- season logic

    def _download_season(self, url: str, path: str | None = None):
        """Write the season metadata and download every episode of a season page."""
        soup = self._fetch_soup(url)
        if soup is None:
            return

        ep_links = soup.find_all("a", class_="ep-tile")
        if not ep_links:
            log_message("No episode links found on the page.")
            return
        log_message(f"Found {len(ep_links)} episode links on the season page.")

        log_message("Extracting generic information about the anime/hentai season.")
        # Reuse what extract_info() already fetched, when available.
        generic_info = self.downloaded_info or self._extract_generic_info(soup)
        if not generic_info:
            log_message("Failed to extract information about the season, using the page title only.")
            generic_info = {"title": self._get_title_from_url(soup)}
        self.downloaded_info = generic_info
        self.d_info = True

        title = generic_info.get("title")
        folder_name = self.sanitize_filename(title)
        season_path = os.path.join(path, folder_name) if path else folder_name
        os.makedirs(season_path, exist_ok=True)
        log_message(f"Download path set to: {season_path}")

        try:
            self._write_tvshow_nfo(generic_info, season_path)
            self._download_jellyfin_images(generic_info, season_path)
        except Exception as e:
            log_message(f"Failed to prepare Jellyfin metadata/images: {e}")

        if self.only_meta_data:
            log_message("Only metadata downloaded, skipping episode downloads as per configuration.")
            return

        log_message(f"Starting download of {len(ep_links)} episodes.")
        for i, ep in enumerate(ep_links, start=1):
            ep_route = str(ep.get("href") or "").strip()
            if not ep_route:
                log_message(f"Episode {i} has no link, skipping it.")
                continue

            # urljoin resolves relative, root-relative and absolute hrefs alike.
            ep_url = urljoin(url, ep_route)
            ep_title = f"{title} - Episode {i}" if title else f"Episode {i}"
            log_message(f"Downloading episode {i}: {ep_title} from URL: {ep_url}")
            self._download_single_episode(ep_url, season_path, ep_title, i)
            log_message(f"Finished downloading episode {i}: {ep_title}")

    def _download_single_episode(self, url: str, path: str, ep_title: str, ep_number: int, season_number: int = 1):
        """Resolve the player page of one episode and download the video."""
        soup = self._fetch_soup(url)
        if soup is None:
            return

        # The "Guarda lo streaming" button points to the page that embeds the
        # actual video player (on some layouts the episode landing page only
        # shows a preview).
        episode_btn = soup.find("a", class_="ept-btn--play") or soup.find("a", class_="ept-btn")
        if episode_btn is None:
            log_message("Could not find the episode link. Please provide the direct episode URL.")
            return

        # .get() can return an AttributeValueList (multi-valued attr), so coerce to str.
        episode_route = str(episode_btn.get("href") or "").strip()
        if not episode_route:
            log_message("Could not find the episode link. Please provide the direct episode URL.")
            return

        # Resolve the play-button href against the episode page URL. urljoin handles
        # absolute URLs, protocol-relative ("//host/path") and root/relative paths.
        episode_url = urljoin(url, episode_route)

        # Video and .nfo must share the same base name for Jellyfin to match them.
        safe_title = self.sanitize_filename(ep_title)
        self._write_episode_nfo(path, safe_title, ep_title, ep_number, season_number)
        self._download_video(episode_url, path, title=safe_title)

    # -------------------------------------------------------- info scraping

    def _extract_generic_info(self, soup_dom) -> dict | None:
        """Run the extractor matching the URL, never raising on layout changes."""
        try:
            if "hentai" in self.url:
                return self._h_info_extractor(soup_dom)
            if "anime" in self.url:
                return self._a_info_extractor(soup_dom)
        except Exception as e:
            log_message(f"Data fetching error: {e}")
            return None

        log_message("Invalid URL provided: no 'anime' or 'hentai' in it.")
        return None

    @staticmethod
    def _get_title_from_url(soup_dom) -> str:
        """Fallback title, used when the extractors fail on a new page layout."""
        title = soup_dom.find("h1", class_="text-2xl")
        if not title:
            log_message("Could not find the title element. Please check the page structure.")
            return "unknown"
        return _text(title) or "unknown"

    @staticmethod
    def _h_info_extractor(soup_dom) -> dict | None:
        """Metadata extractor for HentaiSaturn season pages."""
        external_wrapper = soup_dom.find("div", class_="hs-dhero")
        if not external_wrapper:
            log_message("Could not find the external wrapper. Please check the page structure.")
            return None

        poster_img = _find(_find(external_wrapper, "div", class_="hs-dposter"), "img")
        generic_info = external_wrapper.find("div", class_="flex-1 min-w-0 text-center sm:text-left")
        if not generic_info:
            log_message("Could not find the hero info block. Please check the page structure.")
            return None

        title = generic_info.find("h1", class_="text-2xl")
        # The `hs-hero-meta` spans are positional and not present on every layout.
        hero_meta = generic_info.find_all("span", class_="hs-hero-meta")
        release_date = hero_meta[2] if len(hero_meta) > 2 else None
        tags = generic_info.find_all("a", class_="hs-chip")
        plot = _find(_find(soup_dom, "div", class_="detail-main"), "div", class_="text-sm")
        studio = soup_dom.find("a", href=re.compile(r"^/filter\?studios=\d+"))

        return {
            "anime_poster": poster_img.get("src") if poster_img else None,
            "title": _text(title),
            "release_date": _text(release_date),
            "tags": [tag.get_text(strip=True) for tag in tags] if tags else None,
            "plot": _text(plot),
            "studio": _text(studio),
        }

    @staticmethod
    def _a_info_extractor(soup_dom) -> dict | None:
        """Metadata extractor for AnimeSaturn season pages.

        Not complete yet: the grid/aside classes still have to be double checked
        against the real pages, so every lookup here is null-safe on purpose.
        """
        external_wrapper = soup_dom.find("div", class_="anime-grid")
        if not external_wrapper:
            log_message("Could not find the external wrapper. Please check the page structure.")
            return None

        poster_img = _find(_find(external_wrapper, "div", class_="ag-poster"), "img")
        ag_head = external_wrapper.find("div", class_="ag-head")
        if not ag_head:
            log_message("Could not find the anime grid head. Please check the page structure.")
            return None

        title = ag_head.find("h1", class_="text-2xl")
        alternate_title = ag_head.find("p")

        aside_wrapper = external_wrapper.find("aside")
        if not aside_wrapper:
            log_message("Could not find the aside wrapper. Please check the page structure.")
            return None

        studio = aside_wrapper.find("a", href=re.compile(r"^/filter\?studios=\d+"))
        release_date = _find(
            aside_wrapper.find("div", class_="ag-m-full flex items-center justify-between gap-2 py-0.5"),
            "span",
            class_="font-medium truncate",
        )

        plot = _find(_find(external_wrapper, "section", class_="ag-story"), "div")
        genres_wrapper = external_wrapper.find("div", class_="ag-genres")
        tags = genres_wrapper.find_all("a", class_="hs-chip") if genres_wrapper else []

        return {
            "anime_poster": poster_img.get("src") if poster_img else None,
            "title": _text(title),
            "alternate_title": _text(alternate_title),
            "release_date": _text(release_date),
            "tags": [tag.get_text(strip=True) for tag in tags] if tags else None,
            "plot": _text(plot),
            "studio": _text(studio),
        }

    # ---------------------------------------------------- Jellyfin metadata

    @staticmethod
    def _to_jellyfin_date(value) -> str:
        """Normalise the scraped date to the yyyy-mm-dd Jellyfin expects."""
        if not value:
            return ""

        # Prefer yyyy-mm-dd / yyyy/mm/dd if available in the source text.
        match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        # Fallback for dd-mm-yyyy / dd/mm/yyyy.
        match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", value)
        if match:
            day, month, year = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        # Last fallback: only the year, if present.
        match = re.search(r"(\d{4})", value)
        return match.group(1) if match else ""

    def _write_tvshow_nfo(self, generic_info, anime_path: str):
        """Write the season-level `tvshow.nfo`."""
        info = generic_info or {}
        title = escape(info.get("title") or "Unknown Title")
        plot = escape(info.get("plot") or "")
        studio = escape(info.get("studio") or "")
        release_date = self._to_jellyfin_date(info.get("release_date"))

        genres: list[str] = []
        for item in info.get("tags") or []:
            cleaned = (item or "").strip()
            if cleaned and cleaned not in genres:
                genres.append(cleaned)

        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>',
            "<tvshow>",
            f"  <title>{title}</title>",
        ]
        if plot:
            lines.append(f"  <plot>{plot}</plot>")
        if studio:
            lines.append(f"  <studio>{studio}</studio>")
        if release_date:
            lines.append(f"  <premiered>{escape(release_date)}</premiered>")
            lines.append(f"  <year>{escape(release_date[:4])}</year>")
        for genre in genres:
            lines.append(f"  <genre>{escape(genre)}</genre>")
        lines.append("</tvshow>")

        nfo_path = os.path.join(anime_path, "tvshow.nfo")
        with open(nfo_path, "w", encoding="utf-8") as nfo:
            nfo.write("\n".join(lines) + "\n")


    def _write_episode_nfo(self, anime_path: str, safe_title: str, episode_title: str, episode_number: int, season_number: int = 1):
        """Write the episode-level `.nfo`, named like the video file."""
        nfo_path = os.path.join(anime_path, f"{safe_title}.nfo")
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>',
            "<episodedetails>",
            f"  <title>{escape(episode_title)}</title>",
            f"  <season>{int(season_number)}</season>",
            f"  <episode>{int(episode_number)}</episode>",
            "</episodedetails>",
        ]

        with open(nfo_path, "w", encoding="utf-8") as nfo:
            nfo.write("\n".join(lines) + "\n")

    def _download_jellyfin_images(self, generic_info, anime_path: str):
        """Save the poster as `poster.jpg` next to the NFO files."""
        poster_url = (generic_info or {}).get("anime_poster")
        if not poster_url:
            log_message("No poster URL found, skipping image download.")
            return

        try:
            response = requests.get(poster_url, headers=self.header, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            log_message(f"Failed to download poster image: {e}")
            return

        target_path = os.path.join(anime_path, "poster.jpg")
        with open(target_path, "wb") as image_file:
            image_file.write(response.content)
        log_message(f"Saved image for Jellyfin: {target_path}")

    # ---------------------------------------------------------- video logic

    def _download_video(self, url: str, path: str | None = None, title: str | None = None):
        """Resolve the real stream URL from the player embed and download it with yt-dlp."""
        log_message(f"Starting download for video URL: {url}")
        page_html = self._fetch_text(url)
        if page_html is None:
            return

        soup = BeautifulSoup(page_html, "html.parser")

        # Find the iframe that contains the video player.
        embed_url = None
        for iframe in soup.find_all("iframe"):
            src = str(iframe.get("src") or "")
            if src and ("stream" in src or "embed" in src or "watch" in src):
                embed_url = src
                break

        # Otherwise look for a direct media URL inside the page JavaScript.
        if not embed_url:
            matches = re.findall(r"""https?://[^\s'"]+\.(?:mp4|m3u8)[^\s'"]*""", page_html)
            if matches:
                embed_url = matches[0]

        if not embed_url:
            log_message("Could not automatically find the video URL. Please provide the direct video URL.")
            return

        embed_headers = self._build_headers(embed_url, referer=url)
        direct_stream_url = self._extract_source_from_embed(embed_url, embed_headers)
        log_message(
            f"Direct stream URL extracted: {direct_stream_url}" if direct_stream_url
            else "Could not extract direct stream URL from embed."
        )

        if not direct_stream_url:
            embed_html = self._fetch_text(embed_url, referer=url)
            if embed_html is None:
                return

            video_sources = re.findall(r"""https?://[^\s'"]+\.(?:m3u8|mp4)[^\s'"]*""", embed_html)
            if not video_sources:
                # Some players keep the source in a `file: "..."` JS assignment.
                video_sources = re.findall(r"""file\s*:\s*["']([^"']+)["']""", embed_html)

            if not video_sources:
                log_message("Could not find the video source URL. Please provide the direct video URL.")
                return

            direct_stream_url = video_sources[0]
            log_message(f"Found video source URL: {direct_stream_url}")

        target_path = path or "."
        log_message(f"Setting up yt-dlp options for downloading. Path: {target_path}, Title: {title}")
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "paths": {"home": target_path},
            "outtmpl": f"{title}.%(ext)s" if title else "%(title)s.%(ext)s",
            "http_headers": {
                "User-Agent": DEFAULT_USER_AGENT,
                "Referer": embed_url,
            },
        }
        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                ydl.download([direct_stream_url])
        except Exception as e:
            log_message(f"An error occurred while downloading {url}: {e}")

    def _extract_source_from_embed(self, embed_url: str, headers: dict) -> str | None:
        """Call the embed player's /playlist endpoint and decode the real video URL."""
        parsed = urlparse(embed_url)
        qs = parse_qs(parsed.query)
        token = qs.get("token", [None])[0]
        expires = qs.get("expires", [None])[0]
        if not token or not expires:
            return None

        log_message(f"Extracting source from embed URL: {embed_url}")
        playlist_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}/playlist?token={token}&expires={expires}"
        playlist_headers = headers.copy()
        playlist_headers["Referer"] = embed_url

        try:
            resp = requests.get(playlist_url, headers=playlist_headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log_message(f"Failed to fetch the playlist endpoint: {e}")
            return None
        if resp.status_code != 200:
            log_message(f"The playlist endpoint answered with status code: {resp.status_code}")
            return None

        try:
            data = resp.json()
        except ValueError:
            log_message("The playlist endpoint did not return JSON.")
            return None
        if not isinstance(data, dict):
            return None

        return self._xor_decode(data.get("d"), token)

    @staticmethod
    def _xor_decode(b64_data, key) -> str:
        """Decode the embed player's base64+XOR obfuscated string (dec() in the page JS)."""
        if not b64_data:
            return ""
        # The key is the URL token, so it is deliberately not logged.
        log_message("Decoding the embed player base64+XOR payload.")
        try:
            raw = base64.b64decode(b64_data)
        except Exception as e:
            log_message(f"Failed to base64-decode the player payload: {e}")
            return ""
        return bytes(c ^ ord(key[i % len(key)]) for i, c in enumerate(raw)).decode("utf-8", errors="replace")


def download_animesaturn_season(url: str, path: str | None = None, only_meta_data: bool = False):
    """Transitional functional entry point, kept while the orchestrator is still
    site specific. Prefer `AnimeSaturnDownloader(url, path=path, only_meta_data=...).download()`.
    """
    AnimeSaturnDownloader(url, path=path or "", only_meta_data=only_meta_data).download()
