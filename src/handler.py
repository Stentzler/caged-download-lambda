from typing import Any

from serverless_toolkit.aws.dynamodb import get_dynamodb_table
from serverless_toolkit.aws.s3 import get_s3_client
from serverless_toolkit.observability.lambda_logger import (
    get_lambda_logger,
    inject_lambda_context,
)

from service import DownloadService
from settings import Settings

settings = Settings()
logger = get_lambda_logger()
service = DownloadService(
    settings=settings,
    s3_client=get_s3_client(),
    registry_table=get_dynamodb_table(settings.REGISTRY_TABLE_NAME),
    logger=logger,
)


@inject_lambda_context(logger)
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Download one Novo CAGED archive and upload it to S3."""
    logger.info("Starting CAGED file download")

    try:
        result = service.execute(event)
    except Exception:
        logger.exception("Failed to download CAGED file")
        raise

    logger.info(
        "Finished CAGED file download",
        archive_filename=result["filename"],
        transfer_status=result["status"],
        size_bytes=result.get("size_bytes"),
    )
    return result


lambda_handler = handler
