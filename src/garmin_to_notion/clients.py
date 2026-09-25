"""Garmin and Notion client initialization."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from garminconnect import Garmin as GarminClient
from notion_client import Client as NotionClient

from garmin_to_notion.config import Settings

logger = logging.getLogger(__name__)

TOKENSTORE_DIR = Path(os.getenv("GARMIN_TOKENSTORE", "~/.garmin_tokens")).expanduser()
# File name garminconnect uses when the tokenstore is a directory
TOKEN_FILE = TOKENSTORE_DIR / "garmin_tokens.json"


@dataclass
class Clients:
    garmin: GarminClient
    notion: NotionClient


def _load_tokens_from_env() -> str | None:
    """Load tokens from GARMIN_TOKENS env var (JSON from generate_tokens.py, raw or base64)."""
    raw = os.getenv("GARMIN_TOKENS", "").strip()
    if not raw:
        return None
    try:
        if not raw.startswith("{"):
            raw = base64.b64decode(raw).decode()
        data = json.loads(raw)
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        logger.warning("Failed to decode GARMIN_TOKENS: %s", e)
        return None
    if not isinstance(data, dict) or not data.get("di_refresh_token"):
        logger.warning(
            "GARMIN_TOKENS uses the old OAuth1/OAuth2 format, which Garmin no longer "
            "accepts. Regenerate it with: python scripts/generate_tokens.py"
        )
        return None
    return raw


def _write_token_file(tokens: str) -> None:
    """Write tokens where garminconnect's tokenstore expects them (owner-only)."""
    TOKENSTORE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    TOKEN_FILE.write_text(tokens)
    TOKEN_FILE.chmod(0o600)


def _login_garmin(settings: Settings) -> GarminClient:
    """Log in to Garmin Connect, avoiding Garmin's rate-limited SSO login when possible.

    Auth priority:
    1. Cached tokens on disk (~/.garmin_tokens, carried between runs by actions/cache)
    2. GARMIN_TOKENS env var (tokens generated locally with generate_tokens.py)
    3. Fresh credential login (last resort, Garmin often answers 429 to CI runners)

    garminconnect refreshes expiring tokens and writes them back to the tokenstore,
    so every successful run leaves fresh tokens for the next one.
    """
    token_sources = []
    if TOKEN_FILE.exists():
        token_sources.append(("cached tokens", TOKEN_FILE.read_text()))
    env_tokens = _load_tokens_from_env()
    if env_tokens:
        token_sources.append(("GARMIN_TOKENS secret", env_tokens))

    for source, tokens in token_sources:
        _write_token_file(tokens)
        # No credentials here, so rejected tokens raise and we move on to the next
        # source instead of garminconnect silently falling back to a credential login
        garmin = GarminClient()
        try:
            garmin.login(str(TOKENSTORE_DIR))
            logger.info("Garmin auth successful (%s, user: %s)", source, garmin.display_name)
            return garmin
        except Exception as e:
            logger.warning("Garmin auth with %s failed: %s", source, e)

    TOKEN_FILE.unlink(missing_ok=True)
    garmin = GarminClient(settings.garmin_email, settings.garmin_password)
    try:
        garmin.login(str(TOKENSTORE_DIR))
    except Exception as e:
        logger.error("Failed to authenticate with Garmin Connect: %s", e)
        logger.error(
            "If Garmin keeps rate limiting (429) or asks for MFA, run "
            "scripts/generate_tokens.py on your own computer and save the output "
            "as the GARMIN_TOKENS secret."
        )
        raise SystemExit(1) from e
    logger.info("Garmin auth successful (fresh login, user: %s)", garmin.display_name)
    return garmin


def init_clients(settings: Settings) -> Clients:
    """Initialize and authenticate both Garmin and Notion clients."""
    logger.info("Authenticating with Garmin Connect...")
    garmin = _login_garmin(settings)
    return Clients(garmin=garmin, notion=NotionClient(auth=settings.notion_token))


def init_notion_only(settings: Settings) -> NotionClient:
    """Initialize only the Notion client (for tools that don't need Garmin)."""
    return NotionClient(auth=settings.notion_token)
