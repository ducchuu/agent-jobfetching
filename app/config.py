from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, List, Union
import json

DEFAULT_LOCATIONS: List[str] = [
    "Netherlands",
    "Amsterdam",
    "Utrecht",
    "Rotterdam",
    "Delft",
    "Leiden"
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
    
    LOCATIONS: Union[List[str], str] = Field(default_factory=lambda: list(DEFAULT_LOCATIONS))
    MAX_RESULTS_PER_LOCATION: int = 1000
    SCRAPE_BATCH_SIZE: int = 25
    SCRAPE_DELAY_SECONDS: int = 5
    EVAL_BATCH_SIZE: int = 10
    TARGET_SKILLS_EVALUATIONS: Optional[int] = None

    @field_validator("LOCATIONS", mode="before")
    @classmethod
    def parse_locations(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return list(DEFAULT_LOCATIONS)
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(loc).strip() for loc in parsed if str(loc).strip()]
                except Exception:
                    pass
            return [loc.strip() for loc in v.split(",") if loc.strip()]
        if isinstance(v, list):
            return [str(loc).strip() for loc in v if str(loc).strip()]
        return v
    
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
