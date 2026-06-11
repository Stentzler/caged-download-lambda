import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "local")
    source_name: str = os.getenv("SOURCE_NAME", "boiler-plate")