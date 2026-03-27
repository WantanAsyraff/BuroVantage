"""
VLM Schema Designer - Web UI v3.1 (fixed)
Run: python web_designer.py  →  http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, Response, send_file
from markupsafe import Markup
import json
import threading
import importlib
import queue
import csv
from pathlib import Path
from datetime import datetime

# ── Optional processor import ──────────────────────────────────────────────
try:
    import processor as _processor_module
    PROCESSOR_AVAILABLE = True
except ImportError:
    _processor_module = None
    PROCESSOR_AVAILABLE = False

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_FILE = BASE_DIR / "schema.json"
CONFIG_FILE = BASE_DIR / "config.json"
PDF_DIR = BASE_DIR / "pdfs"

log_queue: queue.Queue = queue.Queue()

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static") if (BASE_DIR / "static").exists() else None
)

# ── Helpers ────────────────────────────────────────────────────────────────

def load_schema() -> list:
    if SCHEMA_FILE.exists():
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("fields", [])
    return []

def save_schema(fields: list) -> None:
    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"document_type": "SAINS Form", "fields": fields},
            f,
            indent=2
        )

def load_config() -> dict:
    default = {
        "provider": "gemini",
        "model": "gemini-1.5-flash",
        "api_keys": {}
    }

    if not CONFIG_FILE.exists():
        return default

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ── Migration safety ─────────────────────────────────────
    if "GEMINI_API_KEY" in data and "api_keys" not in data:
        data["api_keys"] = {"gemini": data.pop("GEMINI_API_KEY")}

    data.setdefault("provider", default["provider"])
    data.setdefault("model", default["model"])
    data.setdefault("api_keys", {})

    return data

def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def push_log(msg: str) -> None:
    log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_csv_files() -> list:
    return sorted([f.name for f in BASE_DIR.glob("extracted_*.csv")])

def read_csv(filename: str) -> dict:
    path = BASE_DIR / filename
    if not path.exists():
        return {"headers": [], "rows": []}

    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if not rows:
        return {"headers": [], "rows": []}

    return {"headers": rows[0], "rows": rows[1:]}

# ── Engine Runner ──────────────────────────────────────────────────────────

def run_engine_thread() -> None:
    try:
        if not PROCESSOR_AVAILABLE:
            push_log("ERROR: processor.py not found.")
            return

        proc = importlib.reload(_processor_module)
        pdfs = list(proc.PDF_DIR.glob("*.pdf"))

        if not pdfs:
            push_log("WARNING: No PDFs found.")
            return

        for pdf in pdfs:
            push_log(f"Processing {pdf.name}...")
            proc.process_pdf(pdf)
            push_log(f"Finished {pdf.name}")

        push_log("All tasks completed successfully.")

    except Exception as e:
        push_log(f"CRITICAL ERROR: {e}")

    finally:
        push_log("__DONE__")

_engine_lock = threading.Event()

# ── Provider Models ────────────────────────────────────────────────────────

PROVIDER_MODELS = {
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite-preview",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4o-2024-11-20",
        "gpt-4.5-preview",
        "o3-mini"
    ],
    "mistral": [
        "pixtral-12b-2409",
        "pixtral-large-2411",
        "mistral-small-2501",
        "pixtral-next-02-06"
    ]
}


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        fields_json=load_schema(),           # raw list
        config_json=load_config(),           # raw dict
        provider_models_json=PROVIDER_MODELS, # raw dict
        proc_status="processor.py ✓" if PROCESSOR_AVAILABLE else "processor.py ✗ missing",
    )

@app.route("/api/schema", methods=["POST"])
def api_save_schema():
    data = request.get_json()
    save_schema(data.get("fields", []))
    push_log("Schema saved.")
    return jsonify({"message": "Schema saved"})

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def api_save_config():
    data = request.get_json()
    save_config(data)
    push_log(f"Config saved: {data.get('provider')} / {data.get('model')}")
    return jsonify({"message": "Saved"})

@app.route("/api/csv-list")
def api_csv_list():
    return jsonify({"files": get_csv_files()})

@app.route("/api/csv")
def api_csv():
    return jsonify(read_csv(request.args.get("file", "")))

@app.route("/api/download-csv")
def api_download_csv():
    filename = request.args.get("file", "")
    path = BASE_DIR / filename

    if not path.exists() or not filename.startswith("extracted_"):
        return "File not found", 404

    return send_file(path, as_attachment=True)

@app.route("/api/pdf-list")
def api_pdf_list():
    if not PDF_DIR.exists():
        return jsonify({"files": []})

    files = []
    for f in sorted(PDF_DIR.glob("*.pdf")):
        size = f.stat().st_size
        files.append({
            "name": f.name,
            "size": f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
        })

    return jsonify({"files": files})

@app.route("/api/upload-pdfs", methods=["POST"])
def api_upload_pdfs():
    PDF_DIR.mkdir(exist_ok=True)

    saved, duplicates = [], []

    for f in request.files.getlist("files"):
        dest = PDF_DIR / f.filename

        if dest.exists():
            duplicates.append(f.filename)
        else:
            f.save(dest)
            saved.append(f.filename)
            push_log(f"Imported: {f.filename}")

    return jsonify({"saved": saved, "duplicates": duplicates})

@app.route("/api/run", methods=["POST"])
def api_run():
    if not _engine_lock.is_set():
        _engine_lock.set()
        threading.Thread(target=lambda: (run_engine_thread(), _engine_lock.clear()), daemon=True).start()

    return jsonify({"status": "started"})

@app.route("/api/logs")
def api_logs():
    def stream():
        while True:
            try:
                msg = log_queue.get(timeout=30)
                yield f"data: {msg}\n\n"
                if "__DONE__" in msg:
                    break
            except queue.Empty:
                yield "data: [ping]\n\n"

    return Response(stream(), mimetype="text/event-stream")

# ── Entry ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PDF_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print(" SAINS Schema Designer UI v3.1 (fixed)")
    print(" http://localhost:5000")
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)