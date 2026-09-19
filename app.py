"""
Flask application — Google Maps Lead Scraper.
Routes: GET /, POST /scrape, POST /export
"""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, render_template, request

from exporter import to_csv, to_xlsx
from scraper import BlockedError, NoResultsError, scrape

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/scrape", methods=["POST"])
def scrape_route() -> Response:
    body     = request.get_json(silent=True) or {}
    category = str(body.get("category", "")).strip()
    location = str(body.get("location", "")).strip()

    if not category or not location:
        return jsonify({"status": "error", "message": "Both category and location are required."}), 400

    if len(category) > 200 or len(location) > 200:
        return jsonify({"status": "error", "message": "Input too long."}), 400

    query = f"{category} in {location}"
    log.info("Scrape requested: %s", query)

    try:
        results = scrape(category, location)
        log.info("Scrape complete: %d results for '%s'", len(results), query)
        return jsonify({"status": "success", "query": query, "results": results})

    except NoResultsError as exc:
        log.warning("No results: %s", exc)
        return jsonify({"status": "error", "message": str(exc)})

    except BlockedError as exc:
        log.warning("Blocked: %s", exc)
        return jsonify({"status": "error", "message": str(exc)})

    except Exception as exc:
        log.error("Unexpected scrape error for '%s': %s", query, exc, exc_info=True)
        return jsonify({"status": "error", "message": "An unexpected error occurred. Please try again."})


@app.route("/export", methods=["POST"])
def export_route() -> Response:
    body    = request.get_json(silent=True) or {}
    results = body.get("results", [])
    fmt     = str(body.get("format", "")).lower().strip()
    query   = str(body.get("query", "leads")).strip()

    if not isinstance(results, list) or not results:
        return jsonify({"status": "error", "message": "No results to export."}), 400

    if fmt not in ("xlsx", "csv"):
        return jsonify({"status": "error", "message": "Format must be 'xlsx' or 'csv'."}), 400

    # Sanitise: keep only expected string fields, cap length
    allowed = {"name", "address", "phone", "website", "rating", "reviews"}
    clean: list[dict] = []
    for row in results:
        if isinstance(row, dict):
            clean.append({k: str(row.get(k, "") or "")[:500] for k in allowed})

    if not clean:
        return jsonify({"status": "error", "message": "No valid results to export."}), 400

    # Build a filesystem-safe filename from the query
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in query)[:50].strip()
    safe = safe or "leads"

    try:
        if fmt == "xlsx":
            data     = to_xlsx(clean, query)
            mime     = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"leads_{safe}.xlsx"
        else:
            data     = to_csv(clean)
            mime     = "text/csv"
            filename = f"leads_{safe}.csv"

        return Response(
            data,
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(data)),
            },
        )

    except Exception as exc:
        log.error("Export error: %s", exc, exc_info=True)
        return jsonify({"status": "error", "message": "Export failed. Please try again."}), 500


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
