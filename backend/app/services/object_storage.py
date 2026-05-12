"""
S3-compatible object storage helpers (AWS S3 / DigitalOcean Spaces).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import boto3
from botocore.client import Config

from ..core.config import settings


import logging
logger = logging.getLogger(__name__)


def s3_enabled() -> bool:
    return settings.STORAGE_TYPE.lower() == "s3"


def _get_s3_client():
    key_id = settings.AWS_ACCESS_KEY_ID or ""
    secret = settings.AWS_SECRET_ACCESS_KEY or ""
    logger.info(
        "S3 client init: key_id=...%s secret_len=%d endpoint=%s region=%s bucket=%s",
        key_id[-6:] if key_id else "MISSING",
        len(secret),
        settings.AWS_S3_ENDPOINT_URL,
        settings.AWS_REGION,
        settings.S3_BUCKET_NAME,
    )
    kwargs = {
        "service_name": "s3",
        "aws_access_key_id": key_id,
        "aws_secret_access_key": secret,
        "region_name": settings.AWS_REGION,
        # path-style addressing is required for DigitalOcean Spaces with a
        # custom endpoint_url — virtual-hosted style causes SignatureDoesNotMatch
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    }
    if settings.AWS_S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT_URL
    return boto3.client(**kwargs)


def make_object_key(opportunity_id: int, category: str, file_name: str) -> str:
    safe_name = file_name.replace("/", "_").replace("\\", "_")
    category = category.strip("/") or "documents"
    return f"{category}/{opportunity_id}/{safe_name}"


def upload_file(local_path: Path, object_key: str, content_type: Optional[str] = None) -> str:
    client = _get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    if extra_args:
        client.upload_file(str(local_path), settings.S3_BUCKET_NAME, object_key, ExtraArgs=extra_args)
    else:
        client.upload_file(str(local_path), settings.S3_BUCKET_NAME, object_key)
    return f"s3://{settings.S3_BUCKET_NAME}/{object_key}"


def upload_bytes(content: bytes, object_key: str, content_type: Optional[str] = None) -> str:
    client = _get_s3_client()
    kwargs = {"Bucket": settings.S3_BUCKET_NAME, "Key": object_key, "Body": content}
    if content_type:
        kwargs["ContentType"] = content_type
    client.put_object(**kwargs)
    return f"s3://{settings.S3_BUCKET_NAME}/{object_key}"


def parse_s3_uri(uri: str) -> Optional[Tuple[str, str]]:
    if not uri or not uri.startswith("s3://"):
        return None
    remainder = uri[5:]
    if "/" not in remainder:
        return None
    bucket, key = remainder.split("/", 1)
    if not bucket or not key:
        return None
    return bucket, key


def delete_s3_uri(uri: str) -> None:
    parsed = parse_s3_uri(uri)
    if not parsed:
        return
    bucket, key = parsed
    client = _get_s3_client()
    client.delete_object(Bucket=bucket, Key=key)


def presigned_get_url(uri: str, expires_seconds: int = 900) -> Optional[str]:
    parsed = parse_s3_uri(uri)
    if not parsed:
        return None
    bucket, key = parsed
    client = _get_s3_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_seconds
    )

def get_s3_object_body(uri: str):
    parsed = parse_s3_uri(uri)
    if not parsed:
        return None
    bucket, key = parsed
    client = _get_s3_client()
    response = client.get_object(Bucket=bucket, Key=key)
    return response['Body']


def read_s3_object(uri: str) -> Optional[tuple]:
    """Read an entire S3 object into memory.

    Returns a (bytes, content_type, content_length) tuple, or None if the URI
    is invalid or the object cannot be retrieved.

    For document serving this is the preferred approach over streaming because:
    - Guarantees complete, untruncated bytes
    - Allows setting Content-Length so browsers/pdf.js know the exact file size
    - Eliminates chunked-encoding edge cases that silently corrupt binary rendering
    """
    parsed = parse_s3_uri(uri)
    if not parsed:
        return None
    bucket, key = parsed
    client = _get_s3_client()
    response = client.get_object(Bucket=bucket, Key=key)
    content_type: str = response.get("ContentType", "application/octet-stream")
    data: bytes = response["Body"].read()
    return data, content_type, len(data)
