from __future__ import annotations
from botocore.config import Config
import boto3
from app.core.config import Config as AppConfig


class R2Storage:
    def __init__(self) -> None:
        endpoint_url = f"https://{AppConfig.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=AppConfig.R2_ACCESS_KEY_ID,
            aws_secret_access_key=AppConfig.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

        self.bucket_name = AppConfig.R2_BUCKET_NAME

    def upload_bytes(self, data: bytes, object_key: str, content_type: str) -> str:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.s3_client.put_object(
            Bucket=self.bucket_name, Key=object_key, Body=data, **extra_args
        )
        return object_key

    def download_bytes(self, object_key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_key)
        return response["Body"].read()
