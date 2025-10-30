import json, re

def strict_json_loads(text: str):
    starts = [m.start() for m in re.finditer(r'\{', text)]
    for s in starts:
        depth = 0
        for i, ch in enumerate(text[s:], start=s):
            if ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    cand = text[s:i+1]
                    try:
                        return json.loads(cand)
                    except Exception:
                        break
    raise ValueError("No valid JSON found in output")
