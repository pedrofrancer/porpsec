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

    # E-mail (Gmail: SMTP para envio, IMAP para ler respostas; senha de app com 2FA)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    EMAIL_ADDRESS: str = ""
    EMAIL_APP_PASSWORD: str = ""
    EMAIL_DAILY_LIMIT: int = 20
    EMAIL_HOURLY_LIMIT: int = 6
    EMAIL_WARMUP_CURVE: str = "5,8,10,12,15,18,20"

    # Identificacao do remetente (rodape legal obrigatorio na UE)
    SENDER_BRAND: str = ""
    SENDER_CONTACT_NAME: str = ""
    SENDER_POSTAL_ADDRESS: str = ""
    SENDER_WEBSITE: str = ""
    OFFER_PRICE_RANGE: str = ""

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context):
        if not self.DATABASE_URL:
            db_path = self.BASE_DIR / "prospectplatform.db"
            self.DATABASE_URL = f"sqlite:///{db_path}"

    @property
    def warmup_curve_list(self) -> list[int]:
        return [int(x.strip()) for x in self.WARMUP_CURVE.split(",")]

    @property
    def email_warmup_curve_list(self) -> list[int]:
        return [int(x.strip()) for x in self.EMAIL_WARMUP_CURVE.split(",")]

    @property
    def email_configured(self) -> bool:
        return bool(self.EMAIL_ADDRESS and self.EMAIL_APP_PASSWORD and self.SENDER_BRAND and self.SENDER_POSTAL_ADDRESS)


settings = Settings()
