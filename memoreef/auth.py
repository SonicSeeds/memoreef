from __future__ import annotations

from pathlib import Path
import secrets
import stat


TOKEN_PREFIX = "mr_"
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "memoreef" / "capture-token"


def generate_capture_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def read_capture_token(path: str | Path = DEFAULT_TOKEN_PATH) -> str | None:
    token_path = Path(path).expanduser()
    if not token_path.exists():
        return None
    token = token_path.read_text(encoding="utf-8").strip()
    return token or None


def ensure_capture_token(path: str | Path = DEFAULT_TOKEN_PATH) -> str:
    token_path = Path(path).expanduser()
    existing = read_capture_token(token_path)
    if existing:
        return existing
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = generate_capture_token()
    token_path.write_text(f"{token}\n", encoding="utf-8")
    try:
        token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return token


def bearer_token_from_header(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if not value.startswith(prefix):
        return None
    token = value[len(prefix) :].strip()
    return token or None
