from abc import abstractmethod


class Downloader:
    url: str
    downloaded_info: dict
    d_info: bool
    header: dict
    path: str
    @abstractmethod
    def is_valid(self, url: str) -> bool:
        pass
    
    @abstractmethod
    def set_all(self, url: str, downloaded_info: dict, d_info: bool, header: dict, path: str):
        self.url = url
        self.downloaded_info = downloaded_info
        self.d_info = d_info
        self.header = header
        self.path = path
        
    @abstractmethod
    def extract_info(self) -> dict | None:
        pass

    @abstractmethod
    def download(self):
        pass
    
    