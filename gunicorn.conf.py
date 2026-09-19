# Gunicorn configuration for Render free tier.
# Scrapes take 70-120s; default 30s timeout kills workers mid-scrape.
timeout = 180
workers = 1
bind = "0.0.0.0:10000"
