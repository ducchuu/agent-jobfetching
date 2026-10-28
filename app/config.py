from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, List
import json

DEFAULT_LOCATIONS: List[str] = [
    "Netherlands",
    "Amsterdam",
    "Utrecht",
    "Rotterdam",
    "Delft",
    "Spain",
    "Barcelona",
    "Madrid"
]

class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    DISCORD_WEBHOOK_URL: str = ""
    MATCH_THRESHOLD: int = 80
    CLOUDFLARE_TUNNEL_TOKEN: str = ""
    API_SECRET_KEY: Optional[str] = None
    
    LOCATIONS: List[str] = Field(default_factory=lambda: list(DEFAULT_LOCATIONS))
    MAX_RESULTS_PER_LOCATION: int = 1000
    SCRAPE_BATCH_SIZE: int = 25
    TARGET_SKILLS_EVALUATIONS: Optional[int] = None

    @field_validator("LOCATIONS", mode="before")
    @classmethod
    def parse_locations(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [loc.strip() for loc in v.split(",") if loc.strip()]
        return v
    
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
