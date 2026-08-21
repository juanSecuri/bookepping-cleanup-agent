"""Google Drive client for LedgerAI (OAuth refresh token or token file)."""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
INGEST_MIMES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
    "audio/webm",
}


@dataclass
class DriveNode:
    id: str
    name: str
    mime_type: str
    path: str
    size: int | None = None
    modified_time: str | None = None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME


class DriveNotConfiguredError(RuntimeError):
    pass


def _token_path() -> Path:
    settings = get_settings()
    if settings.google_drive_token_path:
        return Path(settings.google_drive_token_path)
    return Path(__file__).resolve().parents[3] / ".google_drive_token.json"


def credentials_available() -> bool:
    settings = get_settings()
    if settings.google_oauth_refresh_token.get_secret_value():
        return bool(
            settings.google_oauth_client_id
            and settings.google_oauth_client_secret.get_secret_value()
        )
    return _token_path().exists()


def load_credentials() -> Credentials:
    settings = get_settings()
    refresh = settings.google_oauth_refresh_token.get_secret_value()
    client_id = settings.google_oauth_client_id
    client_secret = settings.google_oauth_client_secret.get_secret_value()

    if refresh and client_id and client_secret:
        creds = Credentials(
            token=None,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds

    path = _token_path()
    if not path.exists():
        raise DriveNotConfiguredError(
            "Google Drive not configured. Run: python -m apps.cli.google_drive_auth "
            "or set GOOGLE_OAUTH_CLIENT_ID / SECRET / REFRESH_TOKEN in .env"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def run_oauth_flow(client_secrets_file: Path) -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
    creds = flow.run_local_server(port=0)
    path = _token_path()
    path.write_text(creds.to_json(), encoding="utf-8")
    return creds


class GoogleDriveClient:
    def __init__(self) -> None:
        self._service = build("drive", "v3", credentials=load_credentials(), cache_discovery=False)

    def get_file(self, file_id: str) -> DriveNode:
        meta = (
            self._service.files()
            .get(
                fileId=file_id,
                fields="id,name,mimeType,size,modifiedTime,parents",
                supportsAllDrives=True,
            )
            .execute()
        )
        return DriveNode(
            id=meta["id"],
            name=meta["name"],
            mime_type=meta["mimeType"],
            path=meta["name"],
            size=int(meta["size"]) if meta.get("size") else None,
            modified_time=meta.get("modifiedTime"),
        )

    def list_children(self, folder_id: str) -> list[DriveNode]:
        items: list[DriveNode] = []
        page_token = None
        query = f"'{folder_id}' in parents and trashed = false"
        while True:
            resp = (
                self._service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id,name,mimeType,size,modifiedTime)",
                    pageSize=100,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="allDrives",
                )
                .execute()
            )
            for f in resp.get("files", []):
                items.append(
                    DriveNode(
                        id=f["id"],
                        name=f["name"],
                        mime_type=f["mimeType"],
                        path=f["name"],
                        size=int(f["size"]) if f.get("size") else None,
                        modified_time=f.get("modifiedTime"),
                    )
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return sorted(items, key=lambda n: (not n.is_folder, n.name.lower()))

    def walk_ingestible(
        self,
        folder_id: str,
        *,
        prefix: str = "",
        max_files: int = 200,
    ) -> Iterator[DriveNode]:
        """Depth-first walk yielding PDFs/images/csv/audio under folder_id."""
        count = 0
        stack: list[tuple[str, str]] = [(folder_id, prefix)]
        while stack and count < max_files:
            current_id, path = stack.pop()
            for node in self.list_children(current_id):
                node_path = f"{path}/{node.name}" if path else node.name
                if node.is_folder:
                    stack.append((node.id, node_path))
                    continue
                if node.mime_type in INGEST_MIMES or node.name.lower().endswith(
                    (
                        ".pdf",
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".csv",
                        ".xlsx",
                        ".xls",
                        ".mp3",
                        ".wav",
                        ".m4a",
                    )
                ):
                    yield DriveNode(
                        id=node.id,
                        name=node.name,
                        mime_type=node.mime_type,
                        path=node_path,
                        size=node.size,
                        modified_time=node.modified_time,
                    )
                    count += 1
                    if count >= max_files:
                        return

    def download_bytes(self, file_id: str) -> bytes:
        request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def browse_tree(self, folder_id: str, *, depth: int = 2) -> dict[str, Any]:
        root = self.get_file(folder_id)
        return self._browse_node(root, depth=depth, path=root.name)

    def _browse_node(self, node: DriveNode, *, depth: int, path: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "mime_type": node.mime_type,
            "path": path,
            "is_folder": node.is_folder,
            "size": node.size,
            "children": [],
        }
        if not node.is_folder or depth <= 0:
            return data
        for child in self.list_children(node.id):
            child_path = f"{path}/{child.name}"
            if child.is_folder:
                data["children"].append(self._browse_node(child, depth=depth - 1, path=child_path))
            else:
                data["children"].append(
                    {
                        "id": child.id,
                        "name": child.name,
                        "mime_type": child.mime_type,
                        "path": child_path,
                        "is_folder": False,
                        "size": child.size,
                    }
                )
        return data
