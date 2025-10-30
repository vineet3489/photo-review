# services/nanobanana_client.py
import os, json, replicate

REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
IMPROVE_MODEL = os.getenv("IMPROVE_MODEL", "google/nano-banana")

IDENTITY_GUARD = (
    "keep same person identity, keep same face, preserve facial features, "
    "preserve skin tone, preserve gender, do not change age or hairstyle"
)

def _pick_url(res):
    if isinstance(res, str): return res
    if isinstance(res, list) and res:
        v = res[0]
        if isinstance(v, str): return v
        if isinstance(v, dict): return v.get("image") or v.get("url") or v.get("output_url") or ""
    if isinstance(res, dict):
        return res.get("image") or res.get("url") or res.get("output_url") or ""
    return ""

def improve_photo(image_url: str, guidance_text: str) -> str:
    client = replicate.Client(api_token=REPLICATE_TOKEN)

    core = f"{IDENTITY_GUARD}. slightly enhance lighting and background. keep clothing natural. {guidance_text}"
    core = " ".join(core.split())[:400]
    base = {"prompt": core, "strength": 0.25}

    candidates = [
        {"image": image_url, **base},
        {"input_image": image_url, **base},
    ]

    last_err = None
    for payload in candidates:
        try:
            out = replicate.run(IMPROVE_MODEL, input=payload)

            # ✅ add this block
            if isinstance(out, str) and out.startswith("http"):
                return out
            # ✅ end addition

            url = _pick_url(out)
            if url:
                return url
            last_err = RuntimeError(f"no url in output: {json.dumps(out)[:300]}")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"NanoBanana failed: {last_err}")

