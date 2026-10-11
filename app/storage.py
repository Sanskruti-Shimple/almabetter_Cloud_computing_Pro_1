import os
import tempfile
from pathlib import Path
from threading import Lock

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from app.config import Settings
from app.models import MusicEvent


_local_lock = Lock()
_blob_service = None


def archive_event(event: MusicEvent, settings: Settings) -> None:
    payload = event.model_dump_json().encode("utf-8")
    blob_name = f"{event.occurred_at:%Y/%m/%d}/{event.event_id}.json"
    if settings.azure_storage_account_url:
        global _blob_service
        if _blob_service is None:
            _blob_service = BlobServiceClient(
                account_url=settings.azure_storage_account_url,
                credential=DefaultAzureCredential(),
            )
        blob = _blob_service.get_blob_client(settings.azure_storage_container, blob_name)
        blob.upload_blob(payload, overwrite=True)
        return

    destination = Path(settings.archive_dir) / blob_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _local_lock:
        descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".event-")
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
