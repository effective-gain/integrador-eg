from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    evolution_api_url: str = ""
    evolution_instance: str = ""
    evolution_api_key: str = ""

    obsidian_api_url: str = "http://localhost:27124"
    obsidian_api_key: str = ""

    gmail_user: str = ""
    gmail_app_password: str = ""
    gmail_imap_host: str = "imap.gmail.com"

    # SMTP (envio de e-mail) — usa mesmas credenciais Gmail por padrão
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""            # se vazio, herda gmail_user
    smtp_password: str = ""        # se vazio, herda gmail_app_password
    email_remetente_nome: str = "Effective Gain"

    # Microsoft 365 / Outlook (Microsoft Graph API — client credentials flow)
    outlook_client_id: str = ""       # Azure AD App Registration → Application (client) ID
    outlook_client_secret: str = ""   # Azure AD App Registration → Client Secret
    outlook_tenant_id: str = ""       # Azure AD → Directory (tenant) ID
    outlook_user_email: str = ""      # Caixa de entrada a ser usada (ex: luiz@effectivegain.com)

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
