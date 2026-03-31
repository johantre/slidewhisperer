import logging
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google import genai
from google.genai import types
import io

load_dotenv()

app = Flask(__name__)

GEMINI_API_KEY        = os.getenv("GEMINI_API_KEY")
SERVICE_ACCOUNT_FILE  = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
OUTPUT_BASE_URL       = os.getenv("OUTPUT_BASE_URL", "http://localhost:5000/output")
OUTPUT_DIR            = Path("output")
UPLOADS_DIR           = Path("uploads")
CACHE_DIR             = Path("cache")
PROMPT_HTML_FILE    = Path("prompts/system_prompt_html.md")
PROMPT_CONTENT_FILE = Path("prompts/system_prompt_content.md")
_PROMPT_LEGACY      = Path("prompts/system_prompt.md")  # migration only

CACHE_DIR.mkdir(exist_ok=True)

# In-memory job status: { job_id: {"status": "running"|"done"|"error", "url": ..., "error": ...} }
jobs: dict = {}


# ── Git versioning voor prompt ─────────────────────────────────────────────────

_GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "SlideWhisperer",
            "GIT_AUTHOR_EMAIL": "app@local",
            "GIT_COMMITTER_NAME": "SlideWhisperer",
            "GIT_COMMITTER_EMAIL": "app@local"}


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        cwd=Path(".").resolve(),
        capture_output=True, text=True,
        env=_GIT_ENV,
    )


def git_ensure_repo():
    app_dir = Path(".").resolve()
    if not (app_dir / ".git").exists():
        _git("init")
        _git("config", "user.email", "app@local")
        _git("config", "user.name", "SlideWhisperer")
        logging.info("Git repo geïnitialiseerd voor prompt-versioning.")
    else:
        _git("config", "user.email", "app@local")
        _git("config", "user.name", "SlideWhisperer")

    new_files = []

    if not PROMPT_CONTENT_FILE.exists():
        PROMPT_CONTENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _PROMPT_LEGACY.exists():
            PROMPT_CONTENT_FILE.write_text(_PROMPT_LEGACY.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            PROMPT_CONTENT_FILE.write_text("", encoding="utf-8")
        new_files.append(str(PROMPT_CONTENT_FILE))
        logging.info(f"Aangemaakt: {PROMPT_CONTENT_FILE}")

    if not PROMPT_HTML_FILE.exists():
        PROMPT_HTML_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROMPT_HTML_FILE.write_text("", encoding="utf-8")
        new_files.append(str(PROMPT_HTML_FILE))
        logging.info(f"Aangemaakt: {PROMPT_HTML_FILE}")

    if new_files:
        for f in new_files:
            _git("add", f)
        result = _git("diff", "--cached", "--quiet")
        if result.returncode != 0:
            _git("commit", "-m", "migratie: split prompt bestanden aangemaakt")


def git_commit_prompt(prompt_file: Path):
    _git("add", str(prompt_file))
    result = _git("diff", "--cached", "--quiet")
    if result.returncode != 0:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        _git("commit", "-m", f"prompt opgeslagen {ts}")
        logging.info("Prompt gecommit.")


def git_log_prompt(prompt_file: Path) -> list[dict]:
    result = _git("log", "--format=%H|%ai", "--follow", "--", str(prompt_file))
    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2:
            full_hash, ts = parts
            commits.append({"hash": full_hash.strip()[:8],
                             "full_hash": full_hash.strip(),
                             "timestamp": ts.strip()})
    return commits


def git_show_prompt(full_hash: str, prompt_file: Path) -> str:
    result = _git("show", f"{full_hash}:{prompt_file}")
    return result.stdout


def git_diff_prompt(full_hash: str, prompt_file: Path) -> str:
    result = _git("diff", full_hash, "--", str(prompt_file))
    return result.stdout


def _is_cancelled(job_id: str) -> bool:
    return jobs.get(job_id, {}).get("cancelled", False)


def _tab_to_file(tab: str) -> Path:
    return PROMPT_HTML_FILE if tab == "html" else PROMPT_CONTENT_FILE


git_ensure_repo()

gemini = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"api_version": "v1beta"},
)


# ── Google Drive helpers ──────────────────────────────────────────────────────

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds)


def extract_folder_id(url: str) -> str:
    """Haal de folder-ID op uit een Google Drive URL."""
    patterns = [
        r"/folders/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Kan geen folder-ID vinden in: {url}")


def get_folder_name(service, folder_id: str) -> str:
    """Haal de mapnaam op uit Drive; geef lege string terug bij fout."""
    try:
        meta = service.files().get(fileId=folder_id, fields="name").execute()
        name = meta.get("name", "").strip()
        # Maak veilig voor gebruik als mapnaam
        name = re.sub(r"[^\w\s-]", "", name)
        name = re.sub(r"\s+", "_", name)
        return name
    except Exception:
        return ""


def list_pdfs(service, folder_id: str) -> list[dict]:
    """Geef alle PDF-bestanden in de map terug."""
    result = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
        fields="files(id, name, modifiedTime)",
        orderBy="name",
    ).execute()
    return result.get("files", [])


def _needs_download(cached_path: Path, drive_mtime_str: str) -> bool:
    """True als cache ontbreekt of Drive-versie nieuwer is dan de cache."""
    if not cached_path.exists():
        return True
    try:
        from datetime import timezone
        drive_mtime = datetime.fromisoformat(drive_mtime_str.replace("Z", "+00:00"))
        local_mtime = datetime.fromtimestamp(cached_path.stat().st_mtime, tz=timezone.utc)
        return drive_mtime > local_mtime
    except Exception:
        return True


def download_pdf(service, file_id: str, dest_path: Path):
    """Download een PDF van Drive naar een lokaal pad."""
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


# ── Gemini helper ─────────────────────────────────────────────────────────────

def generate_html(pdf_paths: list[Path], html_prompt: str, content_prompt: str, job_id: str) -> str:
    """Upload PDFs naar Gemini Files API en genereer HTML."""
    uploaded = []
    try:
        for pdf_path in pdf_paths:
            logging.info(f"[{job_id}] Uploaden naar Gemini: {pdf_path.name}")
            f = gemini.files.upload(
                file=pdf_path,
                config={"mime_type": "application/pdf", "display_name": pdf_path.name},
            )
            uploaded.append(f)

        parts = [types.Part.from_text(text=content_prompt + "\n\nHier zijn de PDF-bestanden van de cursus:\n")]
        for f in uploaded:
            parts.append(types.Part.from_text(text=f"\nBestandsnaam: {f.display_name}\n"))
            parts.append(types.Part.from_uri(file_uri=f.uri, mime_type="application/pdf"))

        logging.info(f"[{job_id}] Gemini genereert HTML…")
        config_kwargs = {"temperature": 0}
        if html_prompt.strip():
            config_kwargs["system_instruction"] = html_prompt
        response = gemini.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=parts,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        html = response.text

    finally:
        # Verwijder geüploade bestanden van Gemini (48u limiet, maar netjes opruimen)
        for f in uploaded:
            try:
                gemini.files.delete(name=f.name)
            except Exception:
                pass

    # Extraheer enkel het HTML-gedeelte (negeer preamble-tekst van Gemini)
    match = re.search(r"<!DOCTYPE html>.*", html, flags=re.DOTALL | re.IGNORECASE)
    if match:
        html = match.group(0)
    # Verwijder eventuele afsluitende markdown code-fencing
    html = re.sub(r"```\s*$", "", html).strip()
    # Injecteer favicon
    html = re.sub(
        r"(<head[^>]*>)",
        r'\1\n  <link rel="icon" type="image/svg+xml" href="/favicon.svg">',
        html, count=1, flags=re.IGNORECASE,
    )
    return html


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/favicon.ico")
@app.route("/favicon.svg")
def favicon():
    return send_from_directory(
        Path("static"), "favicon.svg", mimetype="image/svg+xml"
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/prompt", methods=["GET"])
def get_prompt():
    tab = request.args.get("tab", "content")
    prompt_file = _tab_to_file(tab)
    return prompt_file.read_text(encoding="utf-8"), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/prompt", methods=["POST"])
def save_prompt():
    data = request.get_json()
    tab = (data or {}).get("tab", "content")
    content = (data or {}).get("content", "")
    if content is None:
        return jsonify({"error": "Lege prompt."}), 400
    prompt_file = _tab_to_file(tab)
    prompt_file.write_text(content, encoding="utf-8")
    git_commit_prompt(prompt_file)
    logging.info(f"Prompt opgeslagen en gecommit ({prompt_file.name}).")
    return jsonify({"ok": True})


@app.route("/results")
def list_results():
    results = []
    if OUTPUT_DIR.exists():
        for d in sorted(OUTPUT_DIR.iterdir(),
                        key=lambda x: (x / "overzicht.html").stat().st_mtime if (x / "overzicht.html").exists() else 0,
                        reverse=True):
            html_file = d / "overzicht.html"
            if d.is_dir() and html_file.exists():
                results.append({
                    "id": d.name,
                    "is_preflight": d.name.startswith("pf_"),
                    "mtime": html_file.stat().st_mtime,
                    "url": f"{OUTPUT_BASE_URL}/{d.name}/overzicht.html",
                })
    return jsonify(results)


@app.route("/results/<job_id>", methods=["DELETE"])
def delete_result(job_id):
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.exists() or not job_dir.is_dir():
        return jsonify({"error": "Niet gevonden."}), 404
    # Voorkom path traversal
    if ".." in job_id or "/" in job_id:
        return jsonify({"error": "Ongeldig ID."}), 400
    # Laatste volledige generatie beschermen
    if not job_id.startswith("pf_"):
        full = [d for d in OUTPUT_DIR.iterdir()
                if d.is_dir() and not d.name.startswith("pf_")
                and (d / "overzicht.html").exists()]
        if len(full) <= 1:
            return jsonify({"error": "Laatste overzicht kan niet verwijderd worden."}), 403
    shutil.rmtree(job_dir)
    logging.info(f"Resultaat verwijderd: {job_id}")
    return jsonify({"ok": True})


@app.route("/history")
def history():
    tab = request.args.get("tab", "content")
    return jsonify(git_log_prompt(_tab_to_file(tab)))


@app.route("/history/<hash_>")
def history_content(hash_):
    tab = request.args.get("tab", "content")
    prompt_file = _tab_to_file(tab)
    commits = git_log_prompt(prompt_file)
    full = next((c["full_hash"] for c in commits if c["hash"] == hash_), None)
    if not full:
        return jsonify({"error": "Versie niet gevonden."}), 404
    return git_show_prompt(full, prompt_file), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/history/<hash_>/diff")
def history_diff(hash_):
    tab = request.args.get("tab", "content")
    prompt_file = _tab_to_file(tab)
    commits = git_log_prompt(prompt_file)
    full = next((c["full_hash"] for c in commits if c["hash"] == hash_), None)
    if not full:
        return jsonify({"error": "Versie niet gevonden."}), 404
    return git_diff_prompt(full, prompt_file), 200, {"Content-Type": "text/plain; charset=utf-8"}


def run_preflight(job_id: str, drive_url: str):
    """Zelfde als run_job maar enkel de eerste PDF."""
    try:
        html_prompt    = PROMPT_HTML_FILE.read_text(encoding="utf-8")
        content_prompt = PROMPT_CONTENT_FILE.read_text(encoding="utf-8")

        folder_id = extract_folder_id(drive_url)
        service = get_drive_service()
        pdfs = list_pdfs(service, folder_id)

        if not pdfs:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Geen PDF-bestanden gevonden."
            return

        first = pdfs[0]
        work_dir = UPLOADS_DIR / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        dest   = work_dir / first["name"]
        cached = CACHE_DIR / f"{first['id']}.pdf"
        if cached.exists():
            shutil.copy(cached, dest)
        else:
            download_pdf(service, first["id"], dest)
            shutil.copy(dest, cached)

        logging.info(f"[{job_id}] Preflight met: {first['name']}")
        html = generate_html([dest], html_prompt, content_prompt, job_id)

        job_dir = OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "overzicht.html").write_text(html, encoding="utf-8")
        shutil.copy(dest, job_dir / dest.name)
        shutil.rmtree(work_dir)

        result_url = f"{OUTPUT_BASE_URL}/{job_id}/overzicht.html"
        logging.info(f"[{job_id}] Preflight klaar → {result_url}")
        jobs[job_id]["status"] = "done"
        jobs[job_id]["url"]    = result_url

    except Exception as e:
        logging.exception(f"[{job_id}] Preflight fout")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"]  = str(e)


@app.route("/preflight", methods=["POST"])
def preflight():
    data      = request.get_json()
    drive_url = (data or {}).get("drive_url", "").strip()

    if not drive_url:
        return jsonify({"error": "Geen Drive-URL opgegeven."}), 400

    job_id = "pf_" + uuid.uuid4().hex[:6]
    jobs[job_id] = {"status": "running"}
    threading.Thread(target=run_preflight, args=(job_id, drive_url), daemon=True).start()
    return jsonify({"job_id": job_id})


def run_job(job_id: str, drive_url: str):
    """Draait volledig in een background thread."""
    try:
        folder_id = extract_folder_id(drive_url)
        logging.info(f"[{job_id}] Folder-ID: {folder_id}")

        service = get_drive_service()
        folder_name = get_folder_name(service, folder_id)
        output_id = folder_name if folder_name else job_id
        if folder_name:
            logging.info(f"[{job_id}] Mapnaam voor output: {output_id}")

        job_dir  = OUTPUT_DIR / output_id
        work_dir = UPLOADS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)

        pdfs = list_pdfs(service, folder_id)
        logging.info(f"[{job_id}] {len(pdfs)} PDF(s) gevonden")

        if not pdfs:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"]  = "Geen PDF-bestanden gevonden in deze map."
            return

        pdf_paths = []
        for pdf in pdfs:
            if _is_cancelled(job_id):
                shutil.rmtree(work_dir, ignore_errors=True)
                return
            dest   = work_dir / pdf["name"]
            cached = CACHE_DIR / f"{pdf['id']}.pdf"
            if _needs_download(cached, pdf.get("modifiedTime", "")):
                logging.info(f"[{job_id}] Downloaden: {pdf['name']}")
                download_pdf(service, pdf["id"], dest)
                shutil.copy(dest, cached)
            else:
                logging.info(f"[{job_id}] Cache: {pdf['name']}")
                shutil.copy(cached, dest)
            pdf_paths.append(dest)

        if _is_cancelled(job_id):
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        html_prompt    = PROMPT_HTML_FILE.read_text(encoding="utf-8")
        content_prompt = PROMPT_CONTENT_FILE.read_text(encoding="utf-8")
        logging.info(f"[{job_id}] Gemini wordt aangesproken ({len(pdf_paths)} PDFs)…")
        html = generate_html(pdf_paths, html_prompt, content_prompt, job_id)
        logging.info(f"[{job_id}] HTML gegenereerd ({len(html)} tekens)")

        if _is_cancelled(job_id):
            shutil.rmtree(work_dir, ignore_errors=True)
            return

        (job_dir / "overzicht.html").write_text(html, encoding="utf-8")
        for pdf_path in pdf_paths:
            shutil.copy(pdf_path, job_dir / pdf_path.name)

        shutil.rmtree(work_dir)

        result_url = f"{OUTPUT_BASE_URL}/{output_id}/overzicht.html"
        logging.info(f"[{job_id}] Klaar → {result_url}")
        jobs[job_id]["status"] = "done"
        jobs[job_id]["url"]    = result_url

    except Exception as e:
        logging.exception(f"[{job_id}] Fout in background job")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"]  = str(e)


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    drive_url = (data or {}).get("drive_url", "").strip()

    if not drive_url:
        return jsonify({"error": "Geen Drive-URL opgegeven."}), 400

    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "running"}

    threading.Thread(target=run_job, args=(job_id, drive_url), daemon=True).start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Onbekende job."}), 404
    return jsonify(job)


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Onbekende job."}), 404
    job["cancelled"] = True
    job["status"] = "cancelled"
    return jsonify({"ok": True})


@app.route("/output/<job_id>/<path:filename>")
def serve_output(job_id, filename):
    from flask import send_from_directory
    response = send_from_directory(OUTPUT_DIR / job_id, filename)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.errorhandler(Exception)
def handle_exception(e):
    logging.exception("Onverwachte fout")
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5001, debug=debug)
