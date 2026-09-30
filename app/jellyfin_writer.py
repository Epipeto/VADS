"""Jellyfin metadata writer.

Only the Jellyfin XML (`.nfo`) writing lives here. Everything else is somebody
else's job: the extractors (`extractor/`) build the metadata dict, `downloader.py`
saves the poster image and the videos, `main_download.py` calls both.
"""
import os
import re
from xml.sax.saxutils import escape


def to_jellyfin_date(value) -> str:
    """Normalise a scraped date to the yyyy-mm-dd format Jellyfin expects."""
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


def _genres(tags) -> list[str]:
    """The scraped tags, de-duplicated and without the empty ones."""
    genres: list[str] = []
    for item in tags or []:
        cleaned = (item or "").strip()
        if cleaned and cleaned not in genres:
            genres.append(cleaned)
    return genres


def write_tvshow_nfo(anime_path: str, info: dict | None) -> str:
    """Write the season-level `tvshow.nfo` inside `anime_path`; returns its path."""
    info = info or {}
    title = escape(info.get("title") or "Unknown Title")
    plot = escape(info.get("plot") or "")
    studio = escape(info.get("studio") or "")
    release_date = to_jellyfin_date(info.get("release_date"))

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
    for genre in _genres(info.get("tags")):
        lines.append(f"  <genre>{escape(genre)}</genre>")
    lines.append("</tvshow>")

    nfo_path = os.path.join(anime_path, "tvshow.nfo")
    with open(nfo_path, "w", encoding="utf-8") as nfo:
        nfo.write("\n".join(lines) + "\n")
    return nfo_path


def write_episode_nfo(
    anime_path: str,
    safe_title: str,
    episode_title: str,
    episode_number: int,
    season_number: int = 1,
) -> str:
    """Write the episode-level `.nfo`, named like the video file; returns its path.

    `safe_title` has to match the video file name, otherwise Jellyfin will not
    associate the metadata with the episode.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>',
        "<episodedetails>",
        f"  <title>{escape(episode_title or safe_title)}</title>",
        f"  <season>{int(season_number)}</season>",
        f"  <episode>{int(episode_number)}</episode>",
        "</episodedetails>",
    ]

    nfo_path = os.path.join(anime_path, f"{safe_title}.nfo")
    with open(nfo_path, "w", encoding="utf-8") as nfo:
        nfo.write("\n".join(lines) + "\n")
    return nfo_path
