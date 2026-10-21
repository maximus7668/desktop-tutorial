"""Configuración desde variables de entorno. Ningún secreto se escribe en código ni en logs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Nombres de variables cuyo valor se trata como secreto (se redacta en logs y auditoría).
SECRET_ENV_NAMES = (
    "SECRET_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_API_KEY",
    "SMTP_PASSWORD",
    "ADMIN_PASSWORD",
    "LINKEDIN_ACCESS_TOKEN",
)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    app_env: str = "test"  # test | production
    database_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "test.db")
    secret_key: str = ""
    public_base_url: str = "http://localhost:8000"
    backup_dir: Path = field(default_factory=lambda: BASE_DIR / "backups")
    reports_dir: Path = field(default_factory=lambda: BASE_DIR / "reports")
    initial_capital_eur: float = 0.0

    llm_provider: str = "none"  # none | anthropic | fake (solo pruebas)
    llm_model: str = "claude-opus-5-5"
    # Precios en USD por millón de tokens (configurables: cambian con el tiempo).
    llm_price_in_usd_mtok: float = 4.0
    llm_price_out_usd_mtok: float = 20.0
    usd_to_eur: float = 0.92

    stripe_webhook_secret: str = ""
    owner_legal_name: str = ""
    owner_tax_id: str = ""
    owner_contact_email: str = ""
    owner_address: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def live_data_kind(self) -> str:
        """Datos que entran por HTTP: reales solo en producción."""
        return "real" if self.is_production else "simulation"


def load_dotenv_file(path: Path | None = None) -> None:
    """Carga KEY=VALOR de .env sin pisar variables ya definidas (Docker o el sistema mandan)."""
    path = path or BASE_DIR / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():  # -sig: tolera el BOM del Bloc de notas
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_settings() -> Settings:
    if os.environ.get("APP_SKIP_DOTENV") != "1":
        load_dotenv_file()
    app_env = _env("APP_ENV", "test")
    if app_env not in ("test", "production"):
        raise ValueError("APP_ENV debe ser 'test' o 'production'")
    db_default = BASE_DIR / "data" / f"{app_env}.db"
    s = Settings(
        app_env=app_env,
        database_path=Path(_env("DATABASE_PATH") or db_default),
        secret_key=_env("SECRET_KEY"),
        public_base_url=_env("PUBLIC_BASE_URL", "http://localhost:8000"),
        backup_dir=Path(_env("BACKUP_DIR") or BASE_DIR / "backups"),
        reports_dir=Path(_env("REPORTS_DIR") or BASE_DIR / "reports"),
        initial_capital_eur=float(_env("INITIAL_CAPITAL_EUR", "0")),
        llm_provider=_env("LLM_PROVIDER", "none"),
        llm_model=_env("LLM_MODEL", "claude-opus-5-5"),
        llm_price_in_usd_mtok=float(_env("LLM_PRICE_IN_USD_MTOK", "4")),
        llm_price_out_usd_mtok=float(_env("LLM_PRICE_OUT_USD_MTOK", "20")),
        usd_to_eur=float(_env("USD_TO_EUR", "0.92")),
        stripe_webhook_secret=_env("STRIPE_WEBHOOK_SECRET"),
        owner_legal_name=_env("OWNER_LEGAL_NAME"),
        owner_tax_id=_env("OWNER_TAX_ID"),
        owner_contact_email=_env("OWNER_CONTACT_EMAIL"),
        owner_address=_env("OWNER_ADDRESS"),
    )
    if s.is_production:
        if len(s.secret_key) < 32:
            raise ValueError("En producción SECRET_KEY debe tener al menos 32 caracteres")
        if s.llm_provider == "fake":
            raise ValueError("LLM_PROVIDER=fake no está permitido en producción")
    elif not s.secret_key:
        s.secret_key = "solo-entorno-de-pruebas-no-usar-en-produccion"
    return s
