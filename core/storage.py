"""Cloud storage backends for ImageKit and Cloudinary.

Provides:
- ImageKitStorage: Stores resumes, logos, and documents via ImageKit CDN.
- CloudinaryVideoStorage: Stores and delivers video screenings via Cloudinary.
- Fallback to FileSystemStorage during automated testing or when keys are absent.
"""

from io import BytesIO
import logging
from pathlib import Path
from urllib.parse import urljoin

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

logger = logging.getLogger(__name__)


@deconstructible
class ImageKitStorage(Storage):
    """Storage backend that uploads files to ImageKit and serves them via ImageKit CDN."""

    def __init__(self, **kwargs):
        self._fs = FileSystemStorage()
        self.endpoint = (getattr(settings, "IMAGEKIT_URL_ENDPOINT", "") or "").rstrip("/")
        self.private_key = getattr(settings, "IMAGEKIT_PRIVATE_KEY", "") or ""
        self.is_active = (
            bool(self.endpoint and self.private_key)
            and not getattr(settings, "TESTING", False)
        )
        self._client = None
        if self.is_active:
            try:
                from imagekitio import ImageKit

                self._client = ImageKit(private_key=self.private_key)
            except Exception as exc:
                logger.warning("Could not initialize ImageKit client: %s. Using local storage.", exc)
                self.is_active = False

    def _save(self, name, content):
        if not self.is_active or self._client is None:
            return self._fs._save(name, content)

        # Ensure local file backup is retained for offline extraction / text parsing
        saved_name = self._fs._save(name, content)
        local_path = self._fs.path(saved_name)

        try:
            folder = "/" + str(Path(name).parent).replace("\\", "/")
            if folder == "/.":
                folder = "/"
            file_name = Path(name).name

            with open(local_path, "rb") as fh:
                upload_res = self._client.files.upload(
                    file=fh,
                    file_name=file_name,
                    folder=folder,
                    use_unique_file_name=False,
                )
                logger.info("Uploaded %s to ImageKit (URL: %s)", saved_name, getattr(upload_res, "url", ""))
        except Exception as exc:
            logger.exception("Failed to upload %s to ImageKit, retained local file: %s", saved_name, exc)

        return saved_name

    def _open(self, name, mode="rb"):
        return self._fs._open(name, mode)

    def url(self, name):
        if self.is_active and self.endpoint:
            clean_name = name.lstrip("/")
            return f"{self.endpoint}/{clean_name}"
        return self._fs.url(name)

    def exists(self, name):
        return self._fs.exists(name)

    def delete(self, name):
        return self._fs.delete(name)

    def size(self, name):
        return self._fs.size(name)

    def path(self, name):
        return self._fs.path(name)


@deconstructible
class CloudinaryVideoStorage(Storage):
    """Storage backend for video responses utilizing Cloudinary's streaming and video pipeline."""

    def __init__(self, **kwargs):
        self._fs = FileSystemStorage()
        self.cloud_name = getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or ""
        self.api_key = getattr(settings, "CLOUDINARY_API_KEY", "") or ""
        self.api_secret = getattr(settings, "CLOUDINARY_API_SECRET", "") or ""
        self.is_active = (
            bool(self.cloud_name and self.api_key and self.api_secret)
            and not getattr(settings, "TESTING", False)
        )
        if self.is_active:
            try:
                import cloudinary

                cloudinary.config(
                    cloud_name=self.cloud_name,
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    secure=True,
                )
            except Exception as exc:
                logger.warning("Could not initialize Cloudinary: %s. Using local storage.", exc)
                self.is_active = False

    def _save(self, name, content):
        saved_name = self._fs._save(name, content)
        if not self.is_active:
            return saved_name

        local_path = self._fs.path(saved_name)
        try:
            import cloudinary.uploader

            public_id = str(Path(saved_name).with_suffix(""))
            with open(local_path, "rb") as fh:
                res = cloudinary.uploader.upload_large(
                    fh,
                    resource_type="video",
                    public_id=public_id,
                    overwrite=True,
                )
                logger.info("Uploaded video %s to Cloudinary (URL: %s)", saved_name, res.get("secure_url"))
        except Exception as exc:
            logger.exception("Failed to upload video %s to Cloudinary: %s", saved_name, exc)

        return saved_name

    def _open(self, name, mode="rb"):
        return self._fs._open(name, mode)

    def url(self, name):
        if self.is_active and self.cloud_name:
            import cloudinary.utils

            public_id = str(Path(name).with_suffix(""))
            video_url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="video",
                secure=True,
            )
            if video_url:
                return video_url
        return self._fs.url(name)

    def exists(self, name):
        return self._fs.exists(name)

    def delete(self, name):
        return self._fs.delete(name)

    def size(self, name):
        return self._fs.size(name)

    def path(self, name):
        return self._fs.path(name)
