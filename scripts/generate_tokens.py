"""Generate Garmin tokens locally and output them for the GARMIN_TOKENS GitHub secret.

Garmin often rate limits (429) logins coming from GitHub Actions runners. Logging in
once from your own computer and saving the tokens as a secret lets the workflow skip
the credential login entirely; each run then refreshes and caches the tokens.

Usage:
    python scripts/generate_tokens.py

Reads GARMIN_EMAIL and GARMIN_PASSWORD from .env, or asks for them.
"""

import getpass
import os

from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()

email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
password = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")

print(f"Logging in as {email}...")
garmin = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
garmin.login()
print(f"Login successful! (user: {garmin.display_name})")

token_str = garmin.client.dumps()
print(f"\nToken length: {len(token_str)} chars")
print("\nSet this as your GARMIN_TOKENS GitHub secret:")
print("=" * 60)
print(token_str)
print("=" * 60)
print("\nGitHub: Settings -> Secrets and variables -> Actions -> New repository secret")
