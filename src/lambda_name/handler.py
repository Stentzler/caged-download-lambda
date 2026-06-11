from typing import Any

from serverless_toolkit.observability.lambda_logger import (
    get_lambda_logger,
    inject_lambda_context,
)

from lambda_name.service import BoilerPlateService
from lambda_name.settings import Settings

settings = Settings()
logger = get_lambda_logger()
service = BoilerPlateService(settings=settings)


@inject_lambda_context(logger)
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger.info("Starting boilerplate check")

    result = service.check(event)

    logger.info("Boilerplate check finished", extra={"result": result})

    return result
