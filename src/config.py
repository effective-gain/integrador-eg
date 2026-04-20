from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    openai_api_key: str = ""

    evolution_api_url: str
    evolution_instance: str
    evolution_api_key: str

    obsidian_api_url: str = "http://localhost:27124"
    obsidian_api_key: str

    gmail_user: str = ""
    gmail_app_password: str = ""
    gmail_imap_host: str = "imap.gmail.com"

    briefing_numero_destino: str = ""
    briefing_hora: str = "08:00"

    webhook_secret: str = ""  # header x-webhook-secret da Evolution API

    # integrador-eg-app (dashboard Next.js)
    app_url: str = ""           # ex: https://integrador-app.effectivegain.com
    app_api_key: str = ""       # mesmo valor que INTEGRADOR_API_KEY no Next.js

    log_level: str = "INFO"
    environment: str = "development"

    # painel web (Postgres + sessão)
    database_url: str = ""
    session_secret: str = "dev-insecure-change-me"


settings = Settings()
