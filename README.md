# Google Maps Lead Scraper

A web app that scrapes business leads from Google Maps and exports them to Excel or CSV.

Built with Flask · Playwright · Tailwind CSS · openpyxl

## Live Demo

🔗 **[https://google-maps-lead-scraper.onrender.com](https://google-maps-lead-scraper.onrender.com)**

> First request may take 30–60 s to wake the free-tier instance. Scraping a category takes ~60–90 s.

## Features

- Search any business category + location (e.g. "Gyms in Pune")
- Extracts: Name, Address, Phone, Website, Rating, Reviews
- Up to 20 results per search
- Export to styled `.xlsx` or `.csv`
- Live progress stepper during scrape
- Mobile-responsive UI

## Local Setup

```bash
# 1. Clone
git clone https://github.com/AtharvaJ20/Google_maps_Lead_Scraper.git
cd Google_maps_Lead_Scraper

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser
playwright install chromium

# 5. Run
python app.py
```

Open [http://localhost:5000](http://localhost:5000).

> On Windows with Google Chrome installed, the scraper uses your system Chrome automatically (faster cold start). On Linux/Render it falls back to the Playwright-managed Chromium binary.

## Deployment (Render)

| Setting | Value |
|---------|-------|
| **Runtime** | Python 3 |
| **Build command** | `pip install -r requirements.txt && playwright install chromium` |
| **Start command** | `gunicorn app:app` |
| **Instance type** | Free |

No environment variables required.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1.3, Gunicorn 22 |
| Scraping | Playwright 1.63 (Chromium) |
| Export | openpyxl 3.1.5, csv (stdlib) |
| Frontend | Tailwind CSS (Play CDN), Lucide icons, vanilla JS |

## Screenshot

![Search screen](https://github.com/AtharvaJ20/Google_maps_Lead_Scraper/assets/screenshot.png)
