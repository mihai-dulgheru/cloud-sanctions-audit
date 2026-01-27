"""
DigitalOcean Spaces (S3-compatible) storage utilities.
Handles all file operations for stateless audit storage.
"""

import io
import os
from datetime import datetime, timezone
from typing import Optional, Union

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def get_s3_client():
    """Creates and returns a boto3 S3 client configured for DigitalOcean Spaces."""
    return boto3.client('s3', endpoint_url=os.environ.get('DO_SPACES_ENDPOINT'),
                        region_name=os.environ.get('DO_SPACES_REGION', 'nyc3'),
                        aws_access_key_id=os.environ.get('DO_SPACES_KEY'),
                        aws_secret_access_key=os.environ.get('DO_SPACES_SECRET'),
                        config=Config(signature_version='s3v4'))


def get_bucket_name() -> str:
    """Returns the configured bucket name."""
    return os.environ.get('DO_BUCKET_NAME', 'sanctions-audit')


def upload_to_spaces(file_content: Union[bytes, str], destination_path: str,
                     content_type: str = 'application/octet-stream') -> str:
    """
    Upload bytes or string content directly to DigitalOcean Spaces (in-memory).
    
    Args:
        file_content: Bytes or string content to upload
        destination_path: Full path in the bucket
        content_type: MIME type of the content
        
    Returns:
        The S3 key of the uploaded file
    """
    s3 = get_s3_client()
    bucket = get_bucket_name()

    if isinstance(file_content, str):
        file_content = file_content.encode('utf-8')

    s3.upload_fileobj(io.BytesIO(file_content), bucket, destination_path,
                      ExtraArgs={'ContentType': content_type, 'ACL': 'private'})

    return destination_path


def get_presigned_url(key: str, expiration: int = 3600) -> str:
    """Generate a presigned URL for temporary public access to a file."""
    s3 = get_s3_client()
    bucket = get_bucket_name()

    url = s3.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=expiration)
    return url


def file_exists_in_spaces(key: str) -> bool:
    """Check if a file exists in the Spaces bucket."""
    s3 = get_s3_client()
    bucket = get_bucket_name()

    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise


def download_from_spaces(key: str) -> Optional[bytes]:
    """Download file content from Spaces into memory."""
    s3 = get_s3_client()
    bucket = get_bucket_name()

    try:
        buffer = io.BytesIO()
        s3.download_fileobj(bucket, key, buffer)
        buffer.seek(0)
        return buffer.read()
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return None
        raise


def generate_audit_folder_path(company_or_name: str) -> str:
    """
    Generate the folder path for audit logs.
    Format: {sanitized_entity_name_lowercase}/{YYYYMMDD_HHMMSS}/
    
    Args:
        company_or_name: The company or person name being audited
        
    Returns:
        Folder path string (case-insensitive, lowercase)
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y%m%d_%H%M%S')

    # Sanitize the name for use in path - convert to lowercase for case-insensitive storage
    safe_name = "".join(c if c.isalnum() or c in '-_ ' else '_' for c in company_or_name)
    safe_name = safe_name.strip().replace(' ', '_').lower()  # Lowercase for consistency
    safe_name = safe_name[:50]  # Limit length

    return f"{safe_name}/{timestamp}"
