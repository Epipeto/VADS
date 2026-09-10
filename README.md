# PythonSaturn

Selfhosted downloader for **AnimeSaturn / HentaiSaturn** seasons. Downloads episodes (or metadata only) and generates **Jellyfin-compatible** `tvshow.nfo`, episode NFOs and poster artwork.

- **Backend**: Python + Flask API (`app/`)
- **Frontend**: Vue 3 + TypeScript UI (`ui/`)
- Queue is persisted in `app/download_queue.queue`, settings in `app/.config`, logs in `app/log_file.log`

## Quick start

### 1. Backend

```bash
cd app
pip install -r requirements.txt
python server.py
```

API runs on `http://localhost:5000`.

### 2. Frontend

```bash
cd ui
npm install
npm run dev
```

Open the URL printed by Vite (usually `http://localhost:5173`). Requests to `/api` are proxied to port `5000`.

## Usage

1. Set the **output path** in the UI (where your Jellyfin library lives).
2. Toggle **Metadata only** if you want just NFO/images (no videos).
3. Paste a season URL and add it to the queue.
4. Watch progress in the **Logs** view.

## Notes

- Start the backend before the UI, otherwise the `/api` proxy returns errors.
- Videos are resolved via `yt-dlp`; metadata and images are scraped with `requests` + `BeautifulSoup`.
- Production build: `cd ui && npm run build`.
