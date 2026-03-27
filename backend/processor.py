import csv
import json
import time
import sys
import base64
from datetime import datetime
from pathlib import Path
from io import BytesIO

# ── Configuration & Paths ──────────────────────────────────────────────────
CONFIG_FILE  = Path("config.json")
SCHEMA_FILE  = Path("schema.json")
PDF_DIR      = Path("pdfs")

RENDER_SCALE = 2.0

# ── Provider model catalogues (consumed by web UI for dropdowns) ───────────
PROVIDER_MODELS = {
    "gemini": [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
    ],
    "mistral": [
        "pixtral-12b-2409",
        "pixtral-large-2411",
    ],
}


# ── Helpers ────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"Error: Missing {path}")
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def pil_to_base64(img) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ── Initialise (runs once on import) ──────────────────────────────────────

config = load_json(CONFIG_FILE)
schema = load_json(SCHEMA_FILE)


def build_prompt(s: dict) -> str:
    keys  = [f["key"] for f in s["fields"]] + ["confidence_score"]
    rules = "\n".join(f"- {f['key']}: {f['instruction']}" for f in s["fields"])
    return (
        "Extract data from this image. Return ONLY a JSON list.\n"
        f"Keys: {json.dumps(keys)}\n"
        f"Rules:\n{rules}\n"
        "- confidence_score: integer 1-5"
    )


def build_headers(s: dict) -> list:
    return (
        [f["header"] for f in s["fields"]]
        + ["Manual Entry Checked", "Source File", "Page Number",
           "Extraction Timestamp", "AI Confidence Score"]
    )


PROMPT  = build_prompt(schema)
HEADERS = build_headers(schema)


# ── Provider backends ──────────────────────────────────────────────────────

def call_gemini(api_key: str, model: str, prompt: str, img) -> str:
    from google import genai
    client = genai.Client(api_key=api_key)
    res = client.models.generate_content(model=model, contents=[prompt, img])
    return res.text.strip()


def call_openai(api_key: str, model: str, prompt: str, img) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    b64 = pil_to_base64(img)
    res = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text",      "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]
        }],
        max_tokens=2048,
    )
    return res.choices[0].message.content.strip()


def call_mistral(api_key: str, model: str, prompt: str, img) -> str:
    from mistralai import Mistral
    client = Mistral(api_key=api_key)
    b64 = pil_to_base64(img)
    res = client.chat.complete(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text",      "text": prompt},
                {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
            ]
        }],
    )
    return res.choices[0].message.content.strip()


PROVIDER_FN = {
    "gemini":  call_gemini,
    "openai":  call_openai,
    "mistral": call_mistral,
}


def call_model(prompt: str, img) -> str:
    """Dispatch to the configured provider, reading live config each call."""
    cfg      = load_json(CONFIG_FILE)          # always fresh
    provider = cfg.get("provider", "gemini").lower()
    model    = cfg.get("model", "gemini-1.5-flash")
    api_key  = cfg.get("api_keys", {}).get(provider, "")

    if not api_key:
        raise ValueError(f"No API key configured for provider '{provider}'.")

    fn = PROVIDER_FN.get(provider)
    if not fn:
        raise ValueError(f"Unknown provider '{provider}'.")

    return fn(api_key, model, prompt, img)


# ── JSON cleanup ───────────────────────────────────────────────────────────

def clean_raw(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    return raw


# ── Core processor ────────────────────────────────────────────────────────

def process_pdf(pdf_path: Path) -> None:
    """Extract all pages of *pdf_path* and append results to a CSV."""
    import pypdfium2 as pdfium

    # Reload schema fresh each run so UI edits take effect without restart
    s = load_json(SCHEMA_FILE)
    headers = build_headers(s)
    prompt  = build_prompt(s)

    print(f"--- Processing: {pdf_path.name} ---")

    doc = pdfium.PdfDocument(str(pdf_path))
    out = Path(f"extracted_{pdf_path.stem}.csv")

    if not out.exists():
        with open(out, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)

    for i in range(len(doc)):
        print(f"  [*] Analysing page {i + 1} / {len(doc)} ...")
        img = doc[i].render(scale=RENDER_SCALE).to_pil()

        try:
            raw  = call_model(prompt, img)
            raw  = clean_raw(raw)
            data = json.loads(raw)

            entries = data if isinstance(data, list) else [data]

            with open(out, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for entry in entries:
                    row = [entry.get(field["key"], "") for field in s["fields"]]
                    row += [
                        "No",
                        pdf_path.name,
                        i + 1,
                        datetime.now().strftime("%Y-%m-%d %H:%M"),
                        entry.get("confidence_score", "N/A"),
                    ]
                    writer.writerow(row)

            time.sleep(2)

        except json.JSONDecodeError as e:
            print(f"  [!] JSON parse error on page {i + 1}: {e}")
            print(f"      Raw response: {raw[:200]}")
        except Exception as e:
            print(f"  [!] Error on page {i + 1}: {e}")


# ── CLI entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    if not PDF_DIR.exists():
        PDF_DIR.mkdir()
        print(f"Created {PDF_DIR}/ — place your PDFs there and re-run.")
        sys.exit(0)

    pdfs = list(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in the pdfs/ directory.")
    else:
        for pdf in pdfs:
            process_pdf(pdf)
        print("\n[+] Extraction complete.")