import os
from typing import Tuple
from google.cloud import storage

_bucket = None

def _bucket_handle():
    global _bucket
    if _bucket is None:
        client = storage.Client()
        _bucket = client.bucket(os.environ["GCS_BUCKET"])
    return _bucket

def upload_bytes_and_sign(data: bytes, dest_path: str, content_type: str, expires_sec: int = 3600) -> Tuple[str, str]:
    b = _bucket_handle()
    blob = b.blob(dest_path)
    blob.upload_from_string(data, content_type=content_type)

    # Make object public and return its public URL (no signatures).
    # Works reliably with Firebase Storage buckets.
    blob.acl.save_predefined("publicRead")
    return f"gs://{b.name}/{dest_path}", blob.public_url

