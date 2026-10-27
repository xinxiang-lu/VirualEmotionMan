from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

from flask import current_app


ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg"}
ALLOWED_AVATAR_MIME_TYPES = {"image/jpeg", "image/jpg", "image/pjpeg"}


class OSSServiceUnavailableError(RuntimeError):
    """Raised when optional OSS dependencies are unavailable."""


class OSSService:
    def __init__(self, app=None):
        self.app = app

    def is_configured(self) -> bool:
        config = self._config()
        return all(
            [
                config.get("OSS_ACCESS_KEY_ID"),
                config.get("OSS_ACCESS_KEY_SECRET"),
                config.get("OSS_BUCKET_NAME"),
                config.get("OSS_ENDPOINT"),
            ]
        )

    def upload_avatar(self, file_storage) -> dict:
        oss_sdk = self._sdk()

        if not self.is_configured():
            raise ValueError("OSS 未配置完成，暂时无法上传头像。")

        filename = (file_storage.filename or "").strip()
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix not in ALLOWED_AVATAR_EXTENSIONS:
            raise ValueError("头像仅支持 JPG 或 JPEG 文件。")

        content_type = (file_storage.mimetype or "").lower().strip()
        if content_type and content_type not in ALLOWED_AVATAR_MIME_TYPES:
            raise ValueError("头像文件类型不正确，请上传 JPG 或 JPEG 图片。")

        content = file_storage.read()
        if not content:
            raise ValueError("上传文件为空，请重新选择头像。")

        max_bytes = int(self._config().get("AVATAR_UPLOAD_MAX_MB", 5)) * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"头像文件不能超过 {self._config().get('AVATAR_UPLOAD_MAX_MB', 5)}MB。")

        object_key = self._build_avatar_object_key(suffix or "jpg")
        bucket = self._bucket(oss_sdk)
        headers = {"Content-Type": "image/jpeg"}

        bucket.put_object(object_key, content, headers=headers)
        bucket.put_object_acl(object_key, oss_sdk.OBJECT_ACL_PUBLIC_READ)

        avatar_url = self._public_url(object_key)
        return {
            "objectKey": object_key,
            "avatarUrl": avatar_url,
        }

    def _bucket(self, oss_sdk):
        config = self._config()
        auth = oss_sdk.Auth(config["OSS_ACCESS_KEY_ID"], config["OSS_ACCESS_KEY_SECRET"])
        return oss_sdk.Bucket(auth, config["OSS_ENDPOINT"], config["OSS_BUCKET_NAME"])

    def _public_url(self, object_key: str) -> str:
        config = self._config()
        custom_base = (config.get("OSS_PUBLIC_BASE_URL") or "").strip().rstrip("/")
        if custom_base:
            return f"{custom_base}/{quote(object_key, safe='/')}"

        endpoint = (config.get("OSS_ENDPOINT") or "").strip()
        parsed = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
        scheme = parsed.scheme or "https"
        host = parsed.netloc or parsed.path
        bucket_name = config["OSS_BUCKET_NAME"]
        return f"{scheme}://{bucket_name}.{host}/{quote(object_key, safe='/')}"

    @staticmethod
    def _build_avatar_object_key(extension: str) -> str:
        now = datetime.utcnow()
        return f"avatars/{now:%Y/%m/%d}/{uuid4().hex}.{extension}"

    @staticmethod
    def _config():
        return current_app.config

    @staticmethod
    def _sdk():
        try:
            return import_module("oss2")
        except Exception as error:  # pragma: no cover - environment dependent
            raise OSSServiceUnavailableError("当前环境未启用阿里云 OSS 能力，请安装 oss2 后重试。") from error
