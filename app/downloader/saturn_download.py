from downloader.baseClass import Downloader
import requests
import re
import base64

from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from log_file import log_message


class AnimeSaturnDownloader(Downloader):
    def __init__(self, url: str):
        self.url = url
        self.downloaded_info = {}
        self.d_info = False
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
            "Referer": url
        }   
        self.path = ""

    def is_valid(self, url: str) -> bool:
        # Check if the URL is a valid AnimeSaturn URL
        return "animesaturn" in url or "hentaisaturn" in url
    
    def extract_info(self) -> dict | None:
        if self.d_info:
            return None

        try:
            response = requests.get(self.url, headers=self.header)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            if ("hentai" in self.url):
                generic_info = h_info_extractor(soup)
            elif ("anime" in self.url):
                generic_info = a_info_extractor(soup)
            else:
                log_message("Invalid URL provided")
                return None
            
            return generic_info
        
        except Exception as e:
            log_message(f"Error occurred while fetching the page: {e}")
            
        return None

    def download(self):
        # Implement the logic to download content from the AnimeSaturn URL
        # This could involve downloading video files, metadata, etc.
        pass
    
        
        
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