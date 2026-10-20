import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.actors import agent, human  # noqa: E402
from app.config import Settings  # noqa: E402
from app.core import bootstrap  # noqa: E402

for k in ("ANTHROPIC_API_KEY", "STRIPE_WEBHOOK_SECRET", "LLM_PROVIDER"):
    os.environ.pop(k, None)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="test",
        database_path=tmp_path / "test.db",
        secret_key="clave-de-pruebas-suficientemente-larga-123456",
        backup_dir=tmp_path / "backups",
        reports_dir=tmp_path / "reports",
        owner_legal_name="Titular de Prueba",
        owner_contact_email="titular@example.com",
        owner_tax_id="00000000T",
        owner_address="Calle Ficticia 1",
    )


@pytest.fixture
def conn(settings):
    c = bootstrap(settings)
    yield c
    c.close()


@pytest.fixture
def owner():
    return human("propietario")


@pytest.fixture
def director():
    return agent("director")
