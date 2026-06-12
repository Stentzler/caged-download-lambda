import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    S3_BUCKET_NAME: str = field(default_factory=lambda: os.getenv("S3_BUCKET_NAME", ""))
    REGISTRY_TABLE_NAME: str = field(
        default_factory=lambda: os.getenv(
            "REGISTRY_TABLE_NAME",
            "downloaded_files_registry",
        )
    )
    REGISTRY_ID: str = field(
        default_factory=lambda: os.getenv("REGISTRY_ID", "ftp_tree")
    )
    FTP_TIMEOUT_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("FTP_TIMEOUT_SECONDS", "30"))
    )
    FTP_DOWNLOAD_BLOCK_SIZE: int = field(
        default_factory=lambda: int(os.getenv("FTP_DOWNLOAD_BLOCK_SIZE", "65536"))
    )

    def __post_init__(self) -> None:
        if not self.S3_BUCKET_NAME.strip():
            msg = "S3_BUCKET_NAME must be configured"
            raise ValueError(msg)
        if not self.REGISTRY_TABLE_NAME.strip():
            msg = "REGISTRY_TABLE_NAME must be configured"
            raise ValueError(msg)
        if not self.REGISTRY_ID.strip():
            msg = "REGISTRY_ID must be configured"
            raise ValueError(msg)
        if self.FTP_TIMEOUT_SECONDS < 1:
            msg = "FTP_TIMEOUT_SECONDS must be greater than zero"
            raise ValueError(msg)
        if self.FTP_DOWNLOAD_BLOCK_SIZE < 1:
            msg = "FTP_DOWNLOAD_BLOCK_SIZE must be greater than zero"
            raise ValueError(msg)
