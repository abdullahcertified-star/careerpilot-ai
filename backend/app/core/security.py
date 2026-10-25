import hashlib
import hmac
import os
import secrets
from typing import Tuple


PBKDF2_ITERATIONS = 600_000  # OWASP recommendation for SHA-256
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with cryptographically secure random salt."""
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored PBKDF2-HMAC-SHA256 hash using constant-time comparison."""
    try:
        header, salt_hex, hash_hex = hashed_password.split("$")
        algo_info, iterations_str = header.split(":")[-2], header.split(":")[-1]
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        derived = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(derived, expected_hash)
    except Exception:
        return False


def generate_session_token() -> Tuple[str, str]:
    """
    Generate a secure random session token and its SHA-256 hash.
    The plain token is returned to the client; the hash is stored in the database.
    """
    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)
    return token, token_hash


def hash_session_token(token: str) -> str:
    """Hash a session token with SHA-256 for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
