from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "ProspectPlatform"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = ""

    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    DAILY_SEND_LIMIT: int = 20
    HOURLY_SEND_LIMIT: int = 5

    WHATSAPP_SENDER_URL: str = "http://localhost:3100"

    SEND_WINDOW_START: int = 9
    SEND_WINDOW_END: int = 19

    WARMUP_DAYS: int = 7
    WARMUP_CURVE: str = "5,10,15,20,25,30,40"

    DISPATCHER_INTERVAL_SECONDS: int = 60
    SEND_DELAY_MIN_MS: int = 40000
    SEND_DELAY_MAX_MS: int = 180000

    GOOGLE_MAPS_TIMEOUT: int = 60000

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context):
        if not self.DATABASE_URL:
            db_path = self.BASE_DIR / "prospectplatform.db"
            self.DATABASE_URL = f"sqlite:///{db_path}"

    @property
    def warmup_curve_list(self) -> list[int]:
        return [int(x.strip()) for x in self.WARMUP_CURVE.split(",")]


settings = Settings()
