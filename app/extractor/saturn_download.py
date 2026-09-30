import base64
import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from log_file import log_message

from .baseClass import BaseExtractor

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Requests without a timeout can hang the worker thread forever.
REQUEST_TIMEOUT = 30

# Episode pages end with `/ep-12`: both `/episode/<slug>/ep-12` (landing page)
# and `/hentai/<slug>/ep-12` (page with the player) match. A plain substring
# check on "ep" would also match half of the anime slugs, hence the regex.
EPISODE_URL_RE = re.compile(r"/ep-?(\d+)(?:[/?#]|$)", re.IGNORECASE)


def _find(node, *args, **kwargs):
    """`find` that tolerates a missing parent (returns None instead of raising)."""
    return node.find(*args, **kwargs) if node is not None else None


def _text(node) -> str | None:
    """Stripped text of a tag, or None when the tag is missing."""
    return node.get_text(strip=True) if node is not None else None


class AnimeSaturnDownloader(BaseExtractor):
    """Extractor for AnimeSaturn/HentaiSaturn seasons and single episodes."""

    def __init__(self, url: str = ""):
        super().__init__(url)
        self.header = self._build_headers(url)
        # One-page cache: `extract_info()` and `extract_items()` both need the
        # season page, and it must not be fetched (nor parsed) twice.
        self._cached_url: str | None = None
        self._cached_html: str | None = None
        self._cached_soup: BeautifulSoup | None = None

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

    @staticmethod
    def episode_number(url: str) -> int | None:
        """The episode number carried by the URL (`.../ep-12` -> 12)."""
        match = EPISODE_URL_RE.search(url or "")
        return int(match.group(1)) if match else None

    def extract_info(self) -> dict | None:
        """The Jellyfin metadata of the page, cached in `downloaded_info`.

        A season page carries the full metadata; an episode page only has a
        title, so every other field is simply missing. Returns None when the
        page cannot be fetched.
        """
        if self.d_info:
            return self.downloaded_info

        soup = self._fetch_soup(self.url)
        if soup is None:
            return None

        generic_info = self._extract_generic_info(soup) or self._title_from_page(soup)
        if not generic_info:
            log_message("Failed to extract information about the season.")
            return None

        # Cache the result so a second call does not fetch the page again.
        self.downloaded_info = generic_info
        self.d_info = True
        return generic_info

    def extract_items(self) -> list[dict]:
        """The episodes to handle: every episode of a season, or the episode URL itself."""
        if self.is_episode_url(self.url):
            title = (self.extract_info() or {}).get("title") or "unknown"
            return [self._make_item(title, self.url, self.episode_number(self.url), self.url)]

        soup = self._fetch_soup(self.url)
        if soup is None:
            return []

        ep_links = soup.find_all("a", class_="ep-tile")
        if not ep_links:
            log_message("No episode links found on the page.")
            return []
        log_message(f"Found {len(ep_links)} episode links on the season page.")

        season_title = (self.extract_info() or {}).get("title") or "unknown"
        items: list[dict] = []
        for i, ep in enumerate(ep_links, start=1):
            ep_route = str(ep.get("href") or "").strip()
            if not ep_route:
                log_message(f"Episode {i} has no link, skipping it.")
                continue

            # urljoin resolves relative, root-relative and absolute hrefs alike.
            ep_url = urljoin(self.url, ep_route)
            items.append(self._make_item(f"{season_title} - Episode {i}", ep_url, i, self.url))
        return items

    def extract_download_link(self, item: dict) -> str | None:
        """Resolve the direct stream link of one episode (landing page -> player -> stream)."""
        page_url = str(item.get("page_url") or self.url)
        soup = self._fetch_soup(page_url)
        if soup is None:
            return None

        # The "Guarda lo streaming" button points to the page that embeds the
        # actual video player (on some layouts the episode landing page only
        # shows a preview). On a direct player URL the button is missing, so the
        # page itself is the player.
        player_url = page_url
        episode_btn = soup.find("a", class_="ept-btn--play") or soup.find("a", class_="ept-btn")
        episode_route = str(episode_btn.get("href") or "").strip() if episode_btn is not None else ""
        if episode_route:
            player_url = urljoin(page_url, episode_route)
        else:
            log_message("No player button found on the page, using the page itself as the player.")

        return self._extract_stream_url(player_url, referer=page_url)

    @staticmethod
    def _make_item(title: str, page_url: str, episode: int | None, referer: str) -> dict:
        """The dict `main_download` uses to name and download a single episode."""
        return {
            "title": title,
            "episode": episode,
            "season": 1,
            "page_url": page_url,
            "referer": referer,
        }

    # ------------------------------------------------------- HTTP utilities

    @staticmethod
    def _build_headers(url: str, referer: str | None = None) -> dict:
        """Browser headers for `url`; the referer defaults to the URL itself."""
        return {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": referer or url,
        }

    def _get_page(self, url: str, referer: str | None = None) -> tuple[str | None, BeautifulSoup | None]:
        """GET + parse a page; asking twice for the same URL reuses the first result."""
        if url == self._cached_url:
            return self._cached_html, self._cached_soup

        log_message(f"Fetching page: {url}")
        html: str | None = None
        try:
            response = requests.get(url, headers=self._build_headers(url, referer), timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                log_message(f"Failed to fetch the page {url}. Status code: {response.status_code}")
            else:
                html = response.text
        except requests.RequestException as e:
            log_message(f"Failed to fetch the page {url}: {e}")

        soup = BeautifulSoup(html, "html.parser") if html is not None else None
        self._cached_url, self._cached_html, self._cached_soup = url, html, soup
        return html, soup

    def _fetch_text(self, url: str, referer: str | None = None) -> str | None:
        """The HTML of a page; None on network/HTTP errors."""
        return self._get_page(url, referer)[0]

    def _fetch_soup(self, url: str, referer: str | None = None) -> BeautifulSoup | None:
        """Like `_fetch_text`, but parsed with BeautifulSoup."""
        return self._get_page(url, referer)[1]

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
    def _title_from_page(soup_dom) -> dict | None:
        """Fallback info, used when the extractors fail on a new page layout."""
        title = soup_dom.find("h1", class_="text-2xl")
        if not title:
            log_message("Could not find the title element. Please check the page structure.")
            return None
        return {"title": _text(title) or "unknown"}

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

    # ---------------------------------------------------------- video logic

    def _extract_stream_url(self, url: str, referer: str | None = None) -> str | None:
        """Resolve the direct stream URL of the player page `url` (no download)."""
        log_message(f"Extracting the download link from: {url}")
        page_html, soup = self._get_page(url, referer)
        if page_html is None or soup is None:
            return None

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
            return None

        embed_headers = self._build_headers(embed_url, referer=url)
        direct_stream_url = self._extract_source_from_embed(embed_url, embed_headers)
        log_message(
            f"Direct stream URL extracted: {direct_stream_url}" if direct_stream_url
            else "Could not extract direct stream URL from embed."
        )

        if not direct_stream_url:
            embed_html = self._fetch_text(embed_url, referer=url)
            if embed_html is None:
                return None

            video_sources = re.findall(r"""https?://[^\s'"]+\.(?:m3u8|mp4)[^\s'"]*""", embed_html)
            if not video_sources:
                # Some players keep the source in a `file: "..."` JS assignment.
                video_sources = re.findall(r"""file\s*:\s*["']([^"']+)["']""", embed_html)

            if not video_sources:
                log_message("Could not find the video source URL. Please provide the direct video URL.")
                return None

            direct_stream_url = video_sources[0]
            log_message(f"Found video source URL: {direct_stream_url}")

        return direct_stream_url

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

