from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from exceptions import (
    InvalidDownloadEventError,
    InvalidFTPURLError,
    InvalidRegistryTreeError,
    RegistryItemNotFoundError,
    RegistryUpdateConflictError,
)
from service import DownloadService
from settings import Settings

VALID_EVENT = {
    "filename": "CAGEDMOV202604.7z",
    "ftp_url": (
        "ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED/2026/202604/"
        "CAGEDMOV202604.7z"
    ),
    "reference_month": "202604",
    "reference_year": "2026",
    "s3_key": ("raw/caged/year=2026/month=04/file_type=movement/CAGEDMOV202604.7z"),
}


@dataclass
class FakeLogger:
    entries: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def info(self, message: str, *args: object, **kwargs: object) -> None:
        self.entries.append((message, kwargs))


@dataclass
class FakeS3Client:
    uploads: list[tuple[str, str, str]] = field(default_factory=list)
    error: Exception | None = None

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.uploads.append((filename, bucket, key))
        if self.error:
            raise self.error


@dataclass
class FakeRegistryTable:
    items: list[dict[str, Any]] = field(
        default_factory=lambda: [{"Item": {"registry_id": "ftp_tree", "tree": {}}}]
    )
    update_errors: list[Exception | None] = field(default_factory=list)
    get_calls: list[dict[str, object]] = field(default_factory=list)
    update_calls: list[dict[str, object]] = field(default_factory=list)

    def get_item(self, **kwargs: object) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        index = min(len(self.get_calls) - 1, len(self.items) - 1)
        return self.items[index]

    def update_item(self, **kwargs: object) -> dict[str, Any]:
        self.update_calls.append(kwargs)
        if self.update_errors:
            error = self.update_errors.pop(0)
            if error:
                raise error
        return {}


@dataclass
class FakeFTP:
    content: bytes
    error: Exception | None = None
    commands: list[tuple[str, int]] = field(default_factory=list)
    login_called: bool = False

    def __enter__(self) -> FakeFTP:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def login(self) -> str:
        self.login_called = True
        return "Logged in"

    def retrbinary(self, command: str, callback: Any, blocksize: int = 8192) -> str:
        self.commands.append((command, blocksize))
        if self.error:
            raise self.error
        callback(self.content)
        return "Transfer complete"


def build_service(
    temporary_directory: Path,
    ftp: FakeFTP,
    s3_client: FakeS3Client | None = None,
    registry_table: FakeRegistryTable | None = None,
) -> tuple[DownloadService, FakeS3Client, FakeRegistryTable]:
    effective_s3_client = s3_client or FakeS3Client()
    effective_registry_table = registry_table or FakeRegistryTable()

    def ftp_factory(*args: object, **kwargs: object) -> FakeFTP:
        assert args == ("ftp.mtps.gov.br",)
        assert kwargs == {"timeout": 30, "encoding": "latin-1"}
        return ftp

    service = DownloadService(
        settings=Settings(S3_BUCKET_NAME="caged-raw-data"),
        s3_client=effective_s3_client,
        registry_table=effective_registry_table,
        logger=FakeLogger(),
        ftp_factory=ftp_factory,
        temporary_directory=temporary_directory,
        timestamp_factory=lambda: "2026-06-11T12:00:00Z",
    )
    return service, effective_s3_client, effective_registry_table


def test_execute_downloads_uploads_and_removes_temporary_file(tmp_path: Path) -> None:
    ftp = FakeFTP(content=b"archive-content")
    service, s3_client, registry_table = build_service(tmp_path, ftp)

    response = service.execute(VALID_EVENT)

    temporary_path = tmp_path / VALID_EVENT["filename"]
    assert ftp.login_called
    assert ftp.commands == [
        (
            "RETR /pdet/microdados/NOVO CAGED/2026/202604/CAGEDMOV202604.7z",
            65536,
        )
    ]
    assert s3_client.uploads == [
        (str(temporary_path), "caged-raw-data", VALID_EVENT["s3_key"])
    ]
    assert registry_table.get_calls == [
        {"Key": {"registry_id": "ftp_tree"}, "ConsistentRead": True}
    ]
    assert registry_table.update_calls == [
        {
            "Key": {"registry_id": "ftp_tree"},
            "UpdateExpression": "SET #tree.#year = :value",
            "ConditionExpression": "attribute_not_exists(#tree.#year)",
            "ExpressionAttributeNames": {
                "#tree": "tree",
                "#year": "2026",
            },
            "ExpressionAttributeValues": {
                ":value": {
                    "202604": {
                        "CAGEDMOV202604.7z": {
                            "status": "downloaded",
                            "processing_status": "pending",
                            "process_tag": "2026_04_CAGEDMOV202604.7z",
                            "s3_url": (
                                "s3://caged-raw-data/raw/caged/year=2026/month=04/"
                                "file_type=movement/CAGEDMOV202604.7z"
                            ),
                            "updated_at": "2026-06-11T12:00:00Z",
                        }
                    }
                }
            },
        }
    ]
    assert not temporary_path.exists()
    assert response == {
        "status": "downloaded",
        "filename": "CAGEDMOV202604.7z",
        "reference_month": "202604",
        "reference_year": "2026",
        "s3_bucket": "caged-raw-data",
        "s3_key": VALID_EVENT["s3_key"],
        "size_bytes": 15,
    }


@pytest.mark.parametrize("registry_status", ["downloaded", "skipped"])
def test_execute_skips_file_already_processed_in_registry(
    tmp_path: Path,
    registry_status: str,
) -> None:
    registry_table = FakeRegistryTable(
        items=[
            {
                "Item": {
                    "registry_id": "ftp_tree",
                    "tree": {
                        "2026": {
                            "202604": {"CAGEDMOV202604.7z": {"status": registry_status}}
                        }
                    },
                }
            }
        ]
    )
    ftp = FakeFTP(content=b"archive-content")
    service, s3_client, registry_table = build_service(
        tmp_path,
        ftp,
        registry_table=registry_table,
    )

    response = service.execute(VALID_EVENT)

    assert response == {
        "status": registry_status,
        "filename": "CAGEDMOV202604.7z",
        "reference_month": "202604",
        "reference_year": "2026",
        "s3_bucket": "caged-raw-data",
        "s3_key": VALID_EVENT["s3_key"],
    }
    assert not ftp.login_called
    assert s3_client.uploads == []
    assert registry_table.update_calls == []


def test_execute_updates_existing_month_file_path(tmp_path: Path) -> None:
    registry_table = FakeRegistryTable(
        items=[
            {
                "Item": {
                    "registry_id": "ftp_tree",
                    "tree": {"2026": {"202604": {}}},
                }
            }
        ]
    )
    service, _, registry_table = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
        registry_table=registry_table,
    )

    service.execute(VALID_EVENT)

    update = registry_table.update_calls[0]
    assert update["UpdateExpression"] == ("SET #tree.#year.#month.#filename = :value")
    assert "ConditionExpression" not in update


def test_process_tag_uses_year_month_and_filename(tmp_path: Path) -> None:
    service, _, registry_table = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
    )

    service.execute(VALID_EVENT)

    year_value = registry_table.update_calls[0]["ExpressionAttributeValues"][":value"]
    entry = year_value["202604"]["CAGEDMOV202604.7z"]
    assert entry["process_tag"] == "2026_04_CAGEDMOV202604.7z"
    assert entry["processing_status"] == "pending"


def test_execute_retries_when_parallel_invocation_creates_year(tmp_path: Path) -> None:
    conditional_error = ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "The conditional request failed",
            }
        },
        "UpdateItem",
    )
    registry_table = FakeRegistryTable(
        items=[
            {"Item": {"registry_id": "ftp_tree", "tree": {}}},
            {
                "Item": {
                    "registry_id": "ftp_tree",
                    "tree": {"2026": {"202604": {}}},
                }
            },
        ],
        update_errors=[conditional_error, None],
    )
    service, _, registry_table = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
        registry_table=registry_table,
    )

    service.execute(VALID_EVENT)

    assert len(registry_table.get_calls) == 2
    assert [call["UpdateExpression"] for call in registry_table.update_calls] == [
        "SET #tree.#year = :value",
        "SET #tree.#year.#month.#filename = :value",
    ]


def test_execute_raises_when_registry_item_is_missing(tmp_path: Path) -> None:
    registry_table = FakeRegistryTable(items=[{}])
    service, s3_client, _ = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
        registry_table=registry_table,
    )

    with pytest.raises(RegistryItemNotFoundError, match="downloaded_files_registry"):
        service.execute(VALID_EVENT)

    assert s3_client.uploads == []


def test_execute_raises_when_registry_tree_is_invalid(tmp_path: Path) -> None:
    registry_table = FakeRegistryTable(
        items=[{"Item": {"registry_id": "ftp_tree", "tree": []}}]
    )
    service, s3_client, _ = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
        registry_table=registry_table,
    )

    with pytest.raises(InvalidRegistryTreeError, match="mapping"):
        service.execute(VALID_EVENT)

    assert s3_client.uploads == []


def test_execute_raises_after_repeated_registry_update_conflicts(
    tmp_path: Path,
) -> None:
    conditional_error = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}},
        "UpdateItem",
    )
    registry_table = FakeRegistryTable(
        items=[{"Item": {"registry_id": "ftp_tree", "tree": {}}}],
        update_errors=[conditional_error, conditional_error, conditional_error],
    )
    service, _, _ = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
        registry_table=registry_table,
    )

    with pytest.raises(RegistryUpdateConflictError, match="after conflicts"):
        service.execute(VALID_EVENT)

    assert not (tmp_path / VALID_EVENT["filename"]).exists()


@pytest.mark.parametrize("missing_field", VALID_EVENT)
def test_execute_rejects_missing_required_fields(
    tmp_path: Path,
    missing_field: str,
) -> None:
    event = {**VALID_EVENT, missing_field: ""}
    service, _, _ = build_service(tmp_path, FakeFTP(content=b"content"))

    with pytest.raises(InvalidDownloadEventError, match=missing_field):
        service.execute(event)


def test_execute_rejects_non_object_event(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path, FakeFTP(content=b"content"))

    with pytest.raises(InvalidDownloadEventError, match="JSON object"):
        service.execute([VALID_EVENT])


@pytest.mark.parametrize("filename", ["../file.7z", "folder/file.7z", ".", ".."])
def test_execute_rejects_unsafe_filename(tmp_path: Path, filename: str) -> None:
    service, _, _ = build_service(tmp_path, FakeFTP(content=b"content"))

    with pytest.raises(InvalidDownloadEventError, match="only a file name"):
        service.execute({**VALID_EVENT, "filename": filename})


@pytest.mark.parametrize(
    "ftp_url",
    [
        "https://ftp.mtps.gov.br/file.7z",
        "ftp:///file.7z",
        "ftp://ftp.mtps.gov.br/other-file.7z",
    ],
)
def test_execute_rejects_invalid_ftp_url(tmp_path: Path, ftp_url: str) -> None:
    service, _, _ = build_service(tmp_path, FakeFTP(content=b"content"))

    with pytest.raises(InvalidFTPURLError):
        service.execute({**VALID_EVENT, "ftp_url": ftp_url})


def test_execute_removes_temporary_file_after_ftp_failure(tmp_path: Path) -> None:
    service, _, registry_table = build_service(
        tmp_path,
        FakeFTP(content=b"", error=RuntimeError("FTP failed")),
    )

    with pytest.raises(RuntimeError, match="FTP failed"):
        service.execute(VALID_EVENT)

    assert not (tmp_path / VALID_EVENT["filename"]).exists()
    assert registry_table.update_calls == []


def test_execute_removes_temporary_file_after_s3_failure(tmp_path: Path) -> None:
    s3_client = FakeS3Client(error=RuntimeError("S3 failed"))
    service, _, registry_table = build_service(
        tmp_path,
        FakeFTP(content=b"content"),
        s3_client,
    )

    with pytest.raises(RuntimeError, match="S3 failed"):
        service.execute(VALID_EVENT)

    assert not (tmp_path / VALID_EVENT["filename"]).exists()
    assert registry_table.update_calls == []


@pytest.mark.parametrize(
    ("settings_kwargs", "message"),
    [
        ({"S3_BUCKET_NAME": ""}, "S3_BUCKET_NAME"),
        (
            {"S3_BUCKET_NAME": "bucket", "REGISTRY_TABLE_NAME": ""},
            "REGISTRY_TABLE_NAME",
        ),
        (
            {"S3_BUCKET_NAME": "bucket", "REGISTRY_ID": ""},
            "REGISTRY_ID",
        ),
        (
            {"S3_BUCKET_NAME": "bucket", "FTP_TIMEOUT_SECONDS": 0},
            "FTP_TIMEOUT_SECONDS",
        ),
        (
            {"S3_BUCKET_NAME": "bucket", "FTP_DOWNLOAD_BLOCK_SIZE": 0},
            "FTP_DOWNLOAD_BLOCK_SIZE",
        ),
    ],
)
def test_settings_rejects_invalid_configuration(
    settings_kwargs: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings(**settings_kwargs)
