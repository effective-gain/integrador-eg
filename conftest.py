"""
conftest.py raiz — seta variáveis de ambiente mínimas para testes.
Necessário para que src.config.Settings() não falhe ao importar api.webhook.
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-anthropic")
os.environ.setdefault("EVOLUTION_API_URL", "https://evolution.test")
os.environ.setdefault("EVOLUTION_INSTANCE", "test-instance")
os.environ.setdefault("EVOLUTION_API_KEY", "evo-test-key")
os.environ.setdefault("OBSIDIAN_API_URL", "http://localhost:27124")
os.environ.setdefault("OBSIDIAN_API_KEY", "obs-test-key")
