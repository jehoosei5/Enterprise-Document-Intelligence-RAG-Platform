"""Document file storage on Cloudflare R2 (S3-compatible object storage).

Railway's container filesystem is ephemeral — anything written to local
disk is gone after the next redeploy. Storing original uploaded files here
instead (a separate, persistent service, the same reasoning as MySQL/Qdrant
already being external) is what makes them survive redeploys.

This is the only module that touches boto3 directly — everything else
(documents.py) goes through the three functions below.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import boto3

from app.core.config import get_settings


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        # R2 only supports (and requires) this signature version.
        region_name="auto",
    )


def object_key(document_id: str, ext: str) -> str:
    return f"documents/{document_id}{ext}"


def upload_file(local_path: Path, key: str) -> None:
    settings = get_settings()
    _client().upload_file(str(local_path), settings.r2_bucket_name, key)


def download_to_temp(key: str, suffix: str = "") -> Path:
    """Fetches the object into a new temp file and returns its path. Caller
    owns cleanup (delete it once done — e.g. via a FastAPI BackgroundTask
    once the response finishes streaming, not before).
    """
    settings = get_settings()
    fd, tmp_path_str = tempfile.mkstemp(suffix=suffix)
    tmp_path = Path(tmp_path_str)
    os.close(fd)
    _client().download_file(settings.r2_bucket_name, key, str(tmp_path))
    return tmp_path


def delete_file(key: str) -> None:
    settings = get_settings()
    _client().delete_object(Bucket=settings.r2_bucket_name, Key=key)
