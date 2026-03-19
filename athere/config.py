import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    handle: str = field(default_factory=lambda: os.environ["ATHERE_HANDLE"])
    app_password: str = field(default_factory=lambda: os.environ["ATHERE_APP_PASSWORD"])
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    lat: float = field(default_factory=lambda: float(os.environ.get("ATHERE_LAT", "0")))
    lng: float = field(default_factory=lambda: float(os.environ.get("ATHERE_LNG", "0")))
    h3_res: int = field(default_factory=lambda: int(os.environ.get("ATHERE_H3_RES", "7")))
