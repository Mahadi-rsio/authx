"""Password hashing and verification (Argon2id via pwdlib)."""

from pwdlib import PasswordHash

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage.

    Plaintext passwords are never stored; only the Argon2id hash is.
    """
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored Argon2id hash."""
    return _password_hasher.verify(password, password_hash)
