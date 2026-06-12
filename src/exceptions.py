class InvalidDownloadEventError(ValueError):
    """Raised when a download invocation does not match the expected contract."""


class InvalidFTPURLError(ValueError):
    """Raised when an FTP URL cannot be downloaded safely."""


class RegistryItemNotFoundError(RuntimeError):
    """Raised when the configured registry item does not exist."""

    def __init__(self, registry_id: str, table_name: str) -> None:
        super().__init__(
            f"Registry item {registry_id!r} was not found in table {table_name!r}."
        )


class InvalidRegistryTreeError(RuntimeError):
    """Raised when the registry tree is not a mapping."""


class RegistryUpdateConflictError(RuntimeError):
    """Raised when concurrent registry initialization repeatedly conflicts."""
