from typing import Any

from lambda_name.settings import Settings


class BoilerPlateService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def check(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "available": False,
            "source": self.settings.source_name,
            "message": "No new file found",
        }