# services/openai_review.py
import os, json, re
from typing import Any, Dict
from openai import OpenAI
from services.utils import strict_json_loads
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

def _extract_json(txt: str) -> Dict[str, Any]:
    try:
        return strict_json_loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m:
            raise ValueError("OpenAI did not return JSON")
        return json.loads(m.group(0))

def _client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)

def _call_openai(model: str, image_url: str) -> str:
    sys = SYSTEM_PROMPT.strip()
    usr = USER_PROMPT_TEMPLATE.format(image_url=image_url).strip()
    resp = _client().chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": [
                {"type": "text", "text": usr},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]}
        ],
    )
    return (resp.choices[0].message.content or "").strip()

def evaluate_image(image_url: str) -> Dict[str, Any]:
    last_err = None
    for model in (os.getenv("REVIEW_MODEL", "gpt-4o"), "gpt-4o-mini"):
        try:
            txt = _call_openai(model, image_url)
            return _extract_json(txt)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"OpenAI review failed: {last_err}")
