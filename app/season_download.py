import requests
from bs4 import BeautifulSoup
import re
import os
from xml.sax.saxutils import escape
from video_download import download_animesaturn_video
from log_file import log_message


def sanitize_filename(name):
    if not name:
        return "unknown"
    # Keep filenames filesystem-safe across platforms.
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", name)
    sanitized = re.sub(r'\s+', " ", sanitized).strip()
    return sanitized or "unknown"


def _to_jellyfin_date(value):
    if not value:
        return ""

    # Prefer yyyy-mm-dd if available in source text.
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    # Fallback for dd-mm-yyyy / dd/mm/yyyy.
    match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", value)
    if match:
        day, month, year = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    # Last fallback: only year if present.
    match = re.search(r"(\d{4})", value)
    return match.group(1) if match else ""


def write_jellyfin_tvshow_nfo(generic_info, anime_path):
    title = escape((generic_info or {}).get("title") or "Unknown Title")
    plot = escape((generic_info or {}).get("plot") or "")
    studio = escape((generic_info or {}).get("studio") or "")
    release_date = _to_jellyfin_date((generic_info or {}).get("release_date"))
    raw_genres = (generic_info or {}).get("tags") or []
    genres = []
    for item in raw_genres:
        cleaned = (item or "").strip()
        if cleaned and cleaned not in genres:
            genres.append(cleaned)

    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>",
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
        if genre:
            lines.append(f"  <genre>{escape(genre)}</genre>")

    lines.append("</tvshow>")

    nfo_path = os.path.join(anime_path, "tvshow.nfo")
    with open(nfo_path, "w", encoding="utf-8") as nfo:
        nfo.write("\n".join(lines) + "\n")

    log_message(f"Jellyfin tvshow.nfo written to: {nfo_path}")


def write_jellyfin_episode_nfo(anime_path, episode_title, episode_number, season_number=1):
    safe_title = sanitize_filename(episode_title)
    nfo_path = os.path.join(anime_path, f"{safe_title}.nfo")

    lines = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\" ?>",
        "<episodedetails>",
        f"  <title>{escape(episode_title)}</title>",
        f"  <season>{int(season_number)}</season>",
        f"  <episode>{int(episode_number)}</episode>",
        "</episodedetails>",
    ]

    with open(nfo_path, "w", encoding="utf-8") as nfo:
        nfo.write("\n".join(lines) + "\n")

    log_message(f"Jellyfin episode NFO written to: {nfo_path}")


def download_jellyfin_images(generic_info, anime_path, headers):
    poster_url = (generic_info or {}).get("anime_poster")
    if not poster_url:
        log_message("No poster URL found, skipping image download.")
        return

    image_targets = ["poster.jpg"]

    try:
        response = requests.get(poster_url, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as e:
        log_message(f"Failed to download poster image: {e}")
        return

    for filename in image_targets:
        target_path = os.path.join(anime_path, filename)
        with open(target_path, "wb") as image_file:
            image_file.write(response.content)
        log_message(f"Saved image for Jellyfin: {target_path}")

def h_info_extractor(soup_dom):
    
    external_wrapper = soup_dom.find('div', class_='hs-dhero')
    if not external_wrapper:
        log_message("Could not find the external wrapper. Please check the page structure.")
        return None
    
    anime_poster = external_wrapper.find('div', class_='hs-dposter').find('img')['src']    
    generic_info = external_wrapper.find('div', class_='flex-1 min-w-0 text-center sm:text-left')
    title = generic_info.find('h1', class_='text-2xl')
    release_date = generic_info.find_all('span', class_='hs-hero-meta')[2]
    tags = generic_info.find_all('a', class_='hs-chip')
    plot = soup_dom.find('div', class_='detail-main').find('div', class_='text-sm')
    studio = soup_dom.find('a', href=re.compile(r"^/filter\?studios=\d+"))
    
    return {
        'anime_poster': anime_poster,
        'title': title.text.strip() if title else None,
        'release_date': release_date.text.strip() if release_date else None,
        'tags': [tag.text.strip() for tag in tags] if tags else None,
        'plot': plot.text.strip() if plot else None,
        'studio': studio.text.strip() if studio else None
    }
    
#Not complete, all code automatic generation is not working, so I will have to do it manually.
def a_info_extractor(soup_dom):
    
    external_wrapper = soup_dom.find('div', class_='anime-grid')
    if not external_wrapper:
        log_message("Could not find the external wrapper. Please check the page structure.")
        return None
    
    anime_poster = external_wrapper.find('div', class_='ag-poster').find('img')['src']
    ag_head = external_wrapper.find('div', class_='ag-head')
    if not ag_head:
        log_message("Could not find the anime grid head. Please check the page structure.")
        return None
    title = ag_head.find('h1', class_='text-2xl')
    alternate_title = ag_head.find('p')
    
    aside_wrapper = external_wrapper.find('aside')
    if not aside_wrapper:
        log_message("Could not find the aside wrapper. Please check the page structure.")
        return None
    
    studio = aside_wrapper.find('a', href=re.compile(r"^/filter\?studios=\d+"))
    release_date = aside_wrapper.find('div', class_='ag-m-full flex items-center justify-between gap-2 py-0.5').find('span', class_='font-medium truncate')
    
    plot = external_wrapper.find('section', class_='ag-story').find('div')
    tags = external_wrapper.find('div', class_='ag-genres').find_all('a', class_='hs-chip')
    
    return {
        'anime_poster': anime_poster,
        'title': title.text.strip() if title else None,
        'alternate_title': alternate_title.text.strip() if alternate_title else None,
        'release_date': release_date.text.strip() if release_date else None,
        'tags': [tag.text.strip() for tag in tags] if tags else None,
        'plot': plot.text.strip() if plot else None,
        'studio': studio.text.strip() if studio else None
    }
    
def download_animesaturn_season(url, path=None):
    
    if "ep" in url:
        log_message("The provided URL is an episode URL. Please provide a season URL instead.")
        return
    website_domain = url.split('/')[2]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',    
        'Referer': url
    }   
    
    log_message(f"Fetching the season page for URL: {url}")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        log_message(f"Failed to fetch the page. Status code: {response.status_code}")
        return
    log_message("Successfully fetched the season page.")
    
    log_message("Parsing the season page HTML.")
    soup = BeautifulSoup(response.text, 'html.parser')
    log_message("Successfully parsed the season page HTML.")
    # Find the anime poster, the img should be inside a div with class 'hs-dposter', so no check for 'img' is needed

    log_message("Extracting episode links from the season page.")
    ep_links = soup.find_all('a', class_='ep-tile')
    if not ep_links:
        log_message("No episode links found on the page.")
        return
    log_message(f"Found {len(ep_links)} episode links on the season page.")
    
    log_message("Extracting generic information about the anime/hentai season.")
    generic_info = {}
    try:
        if "hentai" in url: 
            generic_info = h_info_extractor(soup)
        elif "anime" in url:
            generic_info = a_info_extractor(soup)
    except Exception as e:
        log_message(f"Data fetching error: {e}")
    
    if generic_info:
        log_message(f"Extracted information")
    else:
        log_message("Failed to extract information about the season.")
        return
    
    anime_folder_name = sanitize_filename(generic_info.get('title'))
    path = os.path.join(path, anime_folder_name) if path else anime_folder_name
    os.makedirs(path, exist_ok=True)
    log_message(f"Download path set to: {path}")

    try:
        write_jellyfin_tvshow_nfo(generic_info, path)
        download_jellyfin_images(generic_info, path, headers)
    except Exception as e:
        log_message(f"Failed to prepare Jellyfin metadata/images: {e}")
        
    if not ep_links:
        log_message("No episode links found on the page.")
        return
    
    log_message(f"Starting download of {len(ep_links)} episodes.")
    i = 1
    for ep in ep_links:
        ep_url = ep.get('href')
        ep_title = generic_info['title'] + f" - Episode {i}" if generic_info.get('title') else f"Episode {i}"
        log_message(f"Downloading episode {i}: {ep_title} from URL: https://{website_domain}{ep_url}")
        to_download_single_episode(f"https://{website_domain}{ep_url}", path, headers, ep_title, i)
        log_message(f"Finished downloading episode {i}: {ep_title}")
        i += 1
    
    
def to_download_single_episode(url, path, headers, ep_title, ep_number, season_number=1):
    log_message(f"Fetching the episode page for URL: {url}")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        log_message(f"Failed to fetch the episode page. Status code: {response.status_code}")
        return
    
    log_message("Parsing the episode page HTML of the episode.")
    soup = BeautifulSoup(response.text, 'html.parser')
    episode_route = soup.find('a', class_='ept-btn')['href']
    
    if not episode_route:
        log_message("Could not find the episode link. Please provide the direct episode URL.")
        return
    
    website_domain = url.split('/')[2]
    episode_url = f"https://{website_domain}{episode_route}"
    write_jellyfin_episode_nfo(path, ep_title, ep_number, season_number=season_number)
    download_animesaturn_video(episode_url, path, title=ep_title)
    
    
    

