# Photo Review & Improvement MVP (Replicate-Only)

Uses Replicate for both:
- openai/gpt-4o → Photo analysis + feedback
- google/nano-banana → Photo enhancement

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Fill `.env` with your Replicate token.

## Run
```bash
uvicorn app:app --reload
streamlit run ui.py
```
