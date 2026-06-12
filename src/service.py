from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from ftplib import FTP
from pathlib import Path, PurePath
from typing import Any, BinaryIO, Protocol
from urllib.parse import unquote, urlparse

from botocore.exceptions import ClientError

from exceptions import (
    InvalidDownloadEventError,
    InvalidFTPURLError,
    InvalidRegistryTreeError,
    RegistryItemNotFoundError,
    RegistryUpdateConflictError,
)
from settings import Settings


class FTPClientProtocol(Protocol):
    """Minimal FTP operations required by the download service."""

    def __enter__(self) -> FTPClientProtocol: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def login(self) -> str: ...

    def retrbinary(
        self,
        command: str,
        callback: Callable[[bytes], object],
        blocksize: int = 8192,
    ) -> str: ...


class S3ClientProtocol(Protocol):
    """Minimal S3 operation required by the download service."""

    def upload_file(self, filename: str, bucket: str, key: str) -> None: ...


class RegistryTableProtocol(Protocol):
    """Minimal DynamoDB operations required by the download service."""

    def get_item(self, **kwargs: object) -> dict[str, Any]: ...

    def update_item(self, **kwargs: object) -> dict[str, Any]: ...


class LoggerProtocol(Protocol):
    """Structured logger operations used by the service."""

    def info(self, message: str, *args: object, **kwargs: object) -> None: ...


@dataclass(frozen=True)
class DownloadRequest:
    filename: str
    ftp_url: str
    reference_month: str
    reference_year: str
    s3_key: str

    @classmethod
    def from_event(cls, event: object) -> DownloadRequest:
        """Validate and build a download request from a Lambda event."""
        if not isinstance(event, dict):
            raise InvalidDownloadEventError("Download event must be a JSON object")

        required_fields = (
            "filename",
            "ftp_url",
            "reference_month",
            "reference_year",
            "s3_key",
        )
        invalid_fields = [
            field
            for field in required_fields
            if not isinstance(event.get(field), str) or not event[field].strip()
        ]
        if invalid_fields:
            fields = ", ".join(invalid_fields)
            raise InvalidDownloadEventError(f"Missing or invalid event fields:{fields}")

        filename = event["filename"]
        if PurePath(filename).name != filename or filename in {".", ".."}:
            raise InvalidDownloadEventError("filename must contain only a file name")

        return cls(**{field: event[field] for field in required_fields})


class DownloadService:
    """Download one FTP archive to temporary storage and upload it to S3."""

    PROCESSED_STATUSES = frozenset({"downloaded", "skipped"})
    MAX_REGISTRY_UPDATE_ATTEMPTS = 3

    def __init__(
        self,
        settings: Settings,
        s3_client: S3ClientProtocol,
        registry_table: RegistryTableProtocol,
        logger: LoggerProtocol,
        ftp_factory: Callable[..., FTPClientProtocol] = FTP,
        temporary_directory: Path = Path("/tmp"),
        timestamp_factory: Callable[[], str] | None = None,
    ) -> None:
        self.settings = settings
        self.s3_client = s3_client
        self.registry_table = registry_table
        self.logger = logger
        self.ftp_factory = ftp_factory
        self.temporary_directory = temporary_directory
        self.timestamp_factory = timestamp_factory or current_utc_timestamp

    def execute(self, event: object) -> dict[str, Any]:
        """Download and upload the file described by the invocation event."""
        request = DownloadRequest.from_event(event)
        registry_tree = self._load_registry_tree()
        registry_entry = self._get_registry_entry(registry_tree, request)
        if registry_entry.get("status") in self.PROCESSED_STATUSES:
            self.logger.info(
                "Skipping file already present in registry",
                archive_filename=request.filename,
                registry_status=registry_entry["status"],
            )
            return self._build_response(request, status=registry_entry.get("status"))

        temporary_path = self.temporary_directory / request.filename

        try:
            self._download(request, temporary_path)
            size_bytes = temporary_path.stat().st_size
            self.logger.info(
                "Uploading CAGED archive to S3",
                archive_filename=request.filename,
                s3_bucket=self.settings.S3_BUCKET_NAME,
                s3_key=request.s3_key,
                size_bytes=size_bytes,
            )
            self.s3_client.upload_file(
                str(temporary_path),
                self.settings.S3_BUCKET_NAME,
                request.s3_key,
            )
            self._update_registry(request, registry_tree)
        finally:
            temporary_path.unlink(missing_ok=True)

        return self._build_response(
            request,
            status="downloaded",
            size_bytes=size_bytes,
        )

    def _build_response(
        self,
        request: DownloadRequest,
        status: str,
        size_bytes: int | None = None,
    ) -> dict[str, Any]:
        response = {
            "status": status,
            "filename": request.filename,
            "reference_month": request.reference_month,
            "reference_year": request.reference_year,
            "s3_bucket": self.settings.S3_BUCKET_NAME,
            "s3_key": request.s3_key,
        }
        if size_bytes is not None:
            response["size_bytes"] = size_bytes
        return response

    def _load_registry_tree(self) -> dict[str, Any]:
        response = self.registry_table.get_item(
            Key={"registry_id": self.settings.REGISTRY_ID},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item:
            raise RegistryItemNotFoundError(
                registry_id=self.settings.REGISTRY_ID,
                table_name=self.settings.REGISTRY_TABLE_NAME,
            )

        tree = item.get("tree")
        if not isinstance(tree, dict):
            raise InvalidRegistryTreeError("Registry tree must be a mapping")
        return tree

    def _get_registry_entry(
        self,
        tree: dict[str, Any],
        request: DownloadRequest,
    ) -> dict[str, Any]:
        year = tree.get(request.reference_year, {})
        if not isinstance(year, dict):
            return {}
        month = year.get(request.reference_month, {})
        if not isinstance(month, dict):
            return {}
        entry = month.get(request.filename, {})
        return entry if isinstance(entry, dict) else {}

    def _update_registry(
        self,
        request: DownloadRequest,
        registry_tree: dict[str, Any],
    ) -> None:
        entry = {
            "status": "downloaded",
            "processing_status": "pending",
            "process_tag": self._build_process_tag(request),
            "s3_url": f"s3://{self.settings.S3_BUCKET_NAME}/{request.s3_key}",
            "updated_at": self.timestamp_factory(),
        }

        for _ in range(self.MAX_REGISTRY_UPDATE_ATTEMPTS):
            try:
                self._write_registry_entry(request, registry_tree, entry)
                return
            except ClientError as error:
                if not is_conditional_check_failure(error):
                    raise
                registry_tree = self._load_registry_tree()

        msg = f"Could not update registry for {request.filename!r} after conflicts"
        raise RegistryUpdateConflictError(msg)

    def _build_process_tag(self, request: DownloadRequest) -> str:
        month = request.reference_month[-2:]
        return f"{request.reference_year}_{month}_{request.filename}"

    def _write_registry_entry(
        self,
        request: DownloadRequest,
        tree: dict[str, Any],
        entry: dict[str, str],
    ) -> None:
        year = tree.get(request.reference_year)
        if not isinstance(year, dict):
            self._update_registry_path(
                request,
                update_expression="SET #tree.#year = :value",
                condition_expression="attribute_not_exists(#tree.#year)",
                value={request.reference_month: {request.filename: entry}},
            )
            return

        month = year.get(request.reference_month)
        if not isinstance(month, dict):
            self._update_registry_path(
                request,
                update_expression="SET #tree.#year.#month = :value",
                condition_expression="attribute_not_exists(#tree.#year.#month)",
                value={request.filename: entry},
            )
            return

        self._update_registry_path(
            request,
            update_expression="SET #tree.#year.#month.#filename = :value",
            value=entry,
        )

    def _update_registry_path(
        self,
        request: DownloadRequest,
        update_expression: str,
        value: dict[str, Any],
        condition_expression: str | None = None,
    ) -> None:
        expressions = f"{update_expression} {condition_expression or ''}"
        attribute_names = {
            "#tree": "tree",
            "#year": request.reference_year,
            "#month": request.reference_month,
            "#filename": request.filename,
        }
        kwargs: dict[str, Any] = {
            "Key": {"registry_id": self.settings.REGISTRY_ID},
            "UpdateExpression": update_expression,
            "ExpressionAttributeNames": {
                placeholder: attribute_name
                for placeholder, attribute_name in attribute_names.items()
                if placeholder in expressions
            },
            "ExpressionAttributeValues": {":value": value},
        }
        if condition_expression:
            kwargs["ConditionExpression"] = condition_expression
        self.registry_table.update_item(**kwargs)

    def _download(self, request: DownloadRequest, destination: Path) -> None:
        parsed_url = urlparse(request.ftp_url)
        remote_path = unquote(parsed_url.path)
        if (
            parsed_url.scheme.lower() != "ftp"
            or not parsed_url.hostname
            or not remote_path
        ):
            raise InvalidFTPURLError("ftp_url must be an absolute FTP URL")
        if PurePath(remote_path).name != request.filename:
            raise InvalidFTPURLError("ftp_url file name must match filename")

        self.logger.info(
            f"Downloading CAGED {request.filename} from FTP",
            ftp_host=parsed_url.hostname,
        )
        with destination.open("wb") as destination_file:
            self._retrieve_file(parsed_url.hostname, remote_path, destination_file)

    def _retrieve_file(
        self,
        ftp_host: str,
        remote_path: str,
        destination_file: BinaryIO,
    ) -> None:
        with self.ftp_factory(
            ftp_host,
            timeout=self.settings.FTP_TIMEOUT_SECONDS,
            encoding="latin-1",
        ) as ftp:
            ftp.login()
            ftp.retrbinary(
                f"RETR {remote_path}",
                destination_file.write,
                blocksize=self.settings.FTP_DOWNLOAD_BLOCK_SIZE,
            )


def current_utc_timestamp() -> str:
    """Return the current UTC timestamp in the registry's ISO-8601 format."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_conditional_check_failure(error: ClientError) -> bool:
    """Return whether a DynamoDB write lost a concurrent initialization race."""
    error_code = error.response.get("Error", {}).get("Code")
    return error_code == "ConditionalCheckFailedException"
