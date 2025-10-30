# app.py
import os, uuid, mimetypes, traceback
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from schemas import AnalyzeResponse, ProcessResponse
from services.nanobanana_client import improve_photo
from services.gcs_client import upload_bytes_and_sign

# load env from project root
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)

# choose review provider
if os.getenv("REVIEW_PROVIDER", "replicate").lower() == "openai":
    from services.openai_review import evaluate_image
else:
    from services.replicate_client import evaluate_image

app = FastAPI(title="Photo Review MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def save_to_gcs_and_sign(f: UploadFile) -> dict:
    ext = (f.filename.split(".")[-1] or "jpg").lower()
    key = f"uploads/{uuid.uuid4().hex}.{ext}"
    content = f.file.read()
    ctype = mimetypes.guess_type(f"file.{ext}")[0] or "application/octet-stream"
    gs_uri, signed = upload_bytes_and_sign(content, key, ctype, expires_sec=3600)
    return {"key": key, "gs_uri": gs_uri, "signed_url": signed}

@app.get("/")
def root():
    return {"status": "ok", "endpoints": ["/analyze", "/process", "/docs", "/_debug_env", "/_preflight_url"]}

@app.get("/_debug_env")
def _debug_env():
    import os.path
    return {
        "REVIEW_PROVIDER": os.getenv("REVIEW_PROVIDER"),
        "REVIEW_MODEL": os.getenv("REVIEW_MODEL"),
        "OPENAI_KEY_len": len(os.getenv("OPENAI_API_KEY", "")),
        "REPLICATE_TOKEN_len": len(os.getenv("REPLICATE_API_TOKEN", "")),
        "GCS_BUCKET": os.getenv("GCS_BUCKET"),
        "CREDS_exists": os.path.isfile(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")),
    }

@app.post("/_preflight_url")
async def _preflight_url(file: UploadFile = File(...)):
    try:
        saved = save_to_gcs_and_sign(file)
        return {"signed_url": saved["signed_url"], "gs_uri": saved["gs_uri"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"preflight failed: {e}")

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(files: list[UploadFile] = File(...)):
    try:
        items = []
        for f in files[:3]:
            saved = save_to_gcs_and_sign(f)
            image_url = saved["signed_url"]  # HTTPS signed URL for model fetch
            feedback = evaluate_image(image_url)
            items.append({"filename": f.filename, "image_url": image_url, "feedback": feedback})

        best = max(items, key=lambda x: sum(x["feedback"]["score"].values()) / 4)
        overall = {
            "main_dp_choice": best["feedback"]["photo_title"],
            "main_dp_choice_url": best["image_url"],
            "action_points": best["feedback"]["action_points"],
            "suggested_order": [i["filename"] for i in items],
        }
        return {"items": items, "overall": overall}
    except Exception as e:
        print("[analyze error]", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"analyze failed: {e}")

@app.post("/process", response_model=ProcessResponse)
async def process(files: list[UploadFile] = File(...)):
    try:
        analysis = await analyze(files)
        improvements = []
        for item in analysis["items"]:
            red = item["feedback"]["red_flags"]
            acts = item["feedback"].get("action_points", [])
            guidance = ", ".join(red + acts)[:600]
            try:
                improved_url = improve_photo(item["image_url"], guidance) or ""
                improvements.append({
                    "filename": item["filename"],
                    "original_url": item["image_url"],
                    "improved_url": improved_url,
                    "prompt_used": guidance,
                })
            except Exception as e:
                improvements.append({
                    "filename": item["filename"],
                    "original_url": item["image_url"],
                    "improved_url": "",
                    "prompt_used": guidance,
                    "error": f"nanobanana_failed: {e}",
                })
        return {"analysis": analysis, "improvements": improvements}
    except Exception as e:
        print("[process fatal]", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"process failed: {e}")

