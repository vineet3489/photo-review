import os, replicate, json, re
from services.utils import strict_json_loads
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
REVIEW_MODEL = os.getenv("REVIEW_MODEL", "meta/meta-llama-3.2-11b-vision-instruct")

def _extract_json(txt: str):
    try:
        return strict_json_loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            return json.loads(m.group(0))
        raise ValueError("LLM did not return JSON")

def evaluate_image(image_url: str):
    client = replicate.Client(api_token=REPLICATE_TOKEN)
    system_prompt = SYSTEM_PROMPT.strip()
    user_prompt = USER_PROMPT_TEMPLATE.format(image_url=image_url).strip()

    # Attempt 1: messages schema
    try:
        out = replicate.run(
            REVIEW_MODEL,
            input={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": user_prompt},
                        {"type": "input_image", "image": image_url}
                    ]}
                ]
            }
        )
        txt = "".join(map(str, out)) if isinstance(out, list) else str(out)
        return _extract_json(txt)
    except Exception:
        # Attempt 2: prompt + image fields
        out = replicate.run(
            REVIEW_MODEL,
            input={"prompt": f"{system_prompt}\n\n{user_prompt}\n\nReturn ONLY JSON.", "image": image_url}
        )
        txt = "".join(map(str, out)) if isinstance(out, list) else str(out)
        return _extract_json(txt)
