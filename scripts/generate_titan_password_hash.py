#!/usr/bin/env python3
# =====================================
# Titan Password Hash Generator
# =====================================

"""Generate an Argon2id password hash for Railway (Phase 10.3).

Usage (from the Titan project root)::

    python scripts/generate_titan_password_hash.py

Security rules:
- Never prints the plaintext password
- Never writes the plaintext password to disk
- Never commits the hash to Git automatically
- Rejects weak passwords
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.password_security import hash_password, validate_password_strength


def main() -> int:
    print("Titan — générateur de hash de mot de passe (Argon2id)")
    print("Le mot de passe ne sera jamais affiché ni écrit sur le disque.\n")

    try:
        password = getpass.getpass("Mot de passe: ")
        confirm = getpass.getpass("Confirmer le mot de passe: ")
    except (KeyboardInterrupt, EOFError):
        print("\nAnnulé.")
        return 1

    if password != confirm:
        print("Erreur: les mots de passe ne correspondent pas.")
        return 1

    ok, message = validate_password_strength(password)
    if not ok:
        print(f"Erreur: {message}")
        return 1

    password_hash = hash_password(password)
    # Drop plaintext references as soon as hashing completes.
    del password
    del confirm

    print("\nHash généré (Argon2id):")
    print(password_hash)
    print("\nAjoute ces variables dans Railway → Variables (valeurs secrètes):")
    print("  AUTH_REQUIRED=true")
    print("  TITAN_AUTH_USERNAME=<ton identifiant>")
    print("  TITAN_AUTH_PASSWORD_HASH=<colle le hash ci-dessus>")
    print("  TITAN_WEB_SECRET_KEY=<déjà configuré — ne pas réutiliser comme mot de passe>")
    print("  TITAN_SESSION_IDLE_MINUTES=60")
    print("  TITAN_SESSION_MAX_HOURS=24")
    print("  COOKIE_SECURE=true")
    print("\nNe committe jamais ce hash dans Git. Colle-le uniquement dans Railway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
