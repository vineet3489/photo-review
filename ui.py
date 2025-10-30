import os, requests, streamlit as st

st.set_page_config(page_title="Photo Review & Improvement", layout="wide")
st.title("Photo Review & Improvement MVP")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8001")

# Optional: for local testing, let user paste payment token
st.text_input("Paid token (leave blank if free/test mode)", key="paid_token")

uploaded = st.file_uploader(
    "Upload up to 3 photos",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True
)
col1, col2 = st.columns(2)
analyze = col1.button("Analyze Only")
process = col2.button("Analyze + Improve")

def call_api(endpoint, files):
    fs = [("files", (f.name, f.getvalue(), "image/jpeg")) for f in files]
    token = st.session_state.get("paid_token", "")
    headers = {"X-Paid-Token": token} if token else {}
    r = requests.post(API_BASE + endpoint, files=fs, headers=headers, timeout=600)
    if not r.ok:
        st.error(f"{endpoint} → {r.status_code}: {r.text}")
        r.raise_for_status()
    return r.json()

if uploaded and (analyze or process):
    endpoint = "/analyze" if analyze else "/process"
    with st.spinner("Processing..."):
        data = call_api(endpoint, uploaded)

    analysis = data.get("analysis", data)

    st.subheader("Feedback")
    for item in analysis["items"]:
        st.markdown(f"**{item['filename']}**")
        c1, c2 = st.columns([1, 2])
        c1.image(item["image_url"], use_column_width=True)
        c2.json(item["feedback"])

    st.markdown("### Overall")
    st.json(analysis["overall"])

    if "improvements" in data:
        st.subheader("Improvements")
        for imp in data["improvements"]:
            c1, c2 = st.columns(2)
            c1.image(imp["original_url"], caption="Original", use_column_width=True)
            if imp.get("improved_url"):
                c2.image(imp["improved_url"], caption="Improved", use_column_width=True)
            else:
                c2.info(imp.get("error", "No improved image URL returned."))
            st.code(imp["prompt_used"])
else:
    st.info("Upload images to enable the buttons.")
