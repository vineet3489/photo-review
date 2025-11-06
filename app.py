# app.py
import os
import uuid
import json
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# service hooks already in your repo
# these should remain unchanged:
# - services.openai_review.evaluate_image(image_url: str) -> dict (analysis JSON)
# - services.nanobanana_client.improve_photo(image_url: str, guidance_text: str) -> str (improved image URL)
from services.openai_review import evaluate_image
from services.nanobanana_client import improve_photo

# Storage adapter constants
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local").lower()
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
GCS_BUCKET = os.getenv("GCS_BUCKET")
# for signed URLs
GCS_SIGNED_EXPIRES = int(os.getenv("GCS_SIGNED_EXPIRES", "3600"))

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Photo review & improve API")


# mount local uploads for dev
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# --- Storage helpers ------------------------------------------------------
def _local_save_file(file: UploadFile) -> str:
    """Save file to uploads/ and return local path (filename)."""
    ext = Path(file.filename).suffix or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    out_path = Path(UPLOAD_DIR) / fname
    with out_path.open("wb") as f:
        f.write(file.file.read())
    return fname


def _local_public_url(request: Request, fname: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/uploads/{fname}"


def _gcs_signed_upload_url(filename: str, expires: int = 3600) -> str:
    """
    Create a signed URL to PUT an object into GCS.
    Imports google.cloud only when needed so dev environment without GCS SDK works.
    """
    from google.cloud import storage
    from google.auth.transport import requests as google_requests

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(filename)

    # generate_signed_url for PUT (method='PUT') depends on library version.
    url = blob.generate_signed_url(
        expiration=expires,
        method="PUT",
        content_type="application/octet-stream",
    )
    return url


def _gcs_public_url(filename: str) -> str:
    return f"https://storage.googleapis.com/{GCS_BUCKET}/{filename}"


async def save_upload_and_get_url(request: Request, file: UploadFile) -> str:
    """
    Unified save function. Returns a public URL (or signed URL depending on provider).
    - local: saves to uploads/ and returns http://<host>/uploads/<file>
    - gcs: uploads bytes to bucket and return public URL (or signed URL if configured)
    """
    if STORAGE_PROVIDER == "local":
        fname = _local_save_file(file)
        return _local_public_url(request, fname)

    if STORAGE_PROVIDER == "gcs":
        # when using GCS choose either direct signed upload or server-side upload
        # server-side upload:
        from google.cloud import storage

        data = await file.read()
        ext = Path(file.filename).suffix or ".jpg"
        dest_path = f"uploads/{uuid.uuid4().hex}{ext}"
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(dest_path)
        blob.upload_from_string(data, content_type=file.content_type or "image/jpeg")

        if os.getenv("GCS_SIGNED_URL", "false").lower() == "true":
            # return a signed GET url
            return blob.generate_signed_url(expiration=GCS_SIGNED_EXPIRES)

        return _gcs_public_url(dest_path)

    raise HTTPException(status_code=500, detail="Unsupported STORAGE_PROVIDER")


# --- Preflight endpoint for direct client -> GCS uploads ------------------
@app.post("/_preflight_url")
async def preflight_url(request: Request, file: UploadFile = File(...)):
    """
    Returns a signed PUT url and gs_uri for the caller to upload directly to GCS.
    Only works when STORAGE_PROVIDER=gcs.
    Client should then PUT the file bytes to signed_url.
    """
    if STORAGE_PROVIDER != "gcs":
        # for local dev, behave like a normal upload and return local public URL
        fname = _local_save_file(file)
        return {"signed_url": _local_public_url(request, fname), "gs_uri": None}

    # generate a dest object path and signed PUT url
    ext = Path(file.filename).suffix or ".jpg"
    dest_path = f"uploads/{uuid.uuid4().hex}{ext}"
    signed_url = _gcs_signed_upload_url(dest_path, expires=GCS_SIGNED_EXPIRES)
    gs_uri = f"gs://{GCS_BUCKET}/{dest_path}"
    return {"signed_url": signed_url, "gs_uri": gs_uri}


# --- Analyze endpoint ----------------------------------------------------
@app.post("/analyze")
async def analyze(request: Request, files: List[UploadFile] = File(...)):
    """
    Analyze images only. Returns structured analysis JSON.
    """
    items = []
    for f in files:
        try:
            public_url = await save_upload_and_get_url(request, f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"save failed: {e}")

        # call the review model (LLM with vision)
        try:
            analysis = evaluate_image(public_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"review failed: {e}")

        items.append({"filename": f.filename, "image_url": public_url, "feedback": analysis})

    overall = {
        # Simplified overall structure. If evaluate_image returns a bigger structure, adapt accordingly.
        "items_count": len(items)
    }

    return JSONResponse({"analysis": {"items": items, "overall": overall}})


# --- Process endpoint: analyze + improve ---------------------------------
@app.post("/process")
async def process(request: Request, files: List[UploadFile] = File(...)):
    """
    Runs analyze then improvement. Returns analysis + improvements with improved URLs.
    """
    analysis_items = []
    improvements = []

    for f in files:
        try:
            public_url = await save_upload_and_get_url(request, f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"save failed: {e}")

        # 1) Analyze
        try:
            analysis = evaluate_image(public_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"review failed: {e}")

        analysis_items.append({"filename": f.filename, "image_url": public_url, "feedback": analysis})

        # 2) Improve using the image improver (Replicate model)
        guidance_text = " ".join(analysis.get("overall_suggestions", [])) if isinstance(analysis, dict) else ""
        try:
            improved_url = improve_photo(public_url, guidance_text)
            improvements.append({
                "filename": f.filename,
                "original_url": public_url,
                "improved_url": improved_url,
                "prompt_used": guidance_text
            })
        except Exception as e:
            improvements.append({
                "filename": f.filename,
                "original_url": public_url,
                "improved_url": None,
                "error": str(e),
                "prompt_used": guidance_text
            })

    overall = {"items_count": len(analysis_items)}
    return JSONResponse({"analysis": {"items": analysis_items, "overall": overall}, "improvements": improvements})


# --- Debug endpoint (optional) -------------------------------------------
@app.get("/_debug_env")
def debug_env():
    # Do not expose secrets in production. This is for quick debug only.
    safe = {k: ("***" if k.lower().find("key") >= 0 or k.lower().find("token") >= 0 else v)
            for k, v in os.environ.items() if k.startswith(("REPLICATE", "OPENAI", "GCS", "STORAGE", "RAZORPAY"))}
    return {"provider": STORAGE_PROVIDER, "gcs_bucket": GCS_BUCKET, "env": safe}


# If run directly for local dev
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8001)), reload=True)
