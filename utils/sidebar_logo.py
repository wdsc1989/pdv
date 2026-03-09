"""
Caminho da logo exibida no menu lateral (sidebar).
A logo é armazenada em uploads/logo/ com nome fixo (logo.png, logo.jpg, etc.).
"""
import base64
from pathlib import Path

UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"
LOGO_DIR = UPLOADS_DIR / "logo"
LOGO_BASE = "logo"
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp")


def get_sidebar_logo_path() -> Path | None:
    """
    Retorna o caminho do arquivo de logo do sidebar, se existir.
    Procura por logo.png, logo.jpg, logo.jpeg, logo.webp em uploads/logo/.
    """
    if not LOGO_DIR.exists():
        return None
    for ext in ALLOWED_EXT:
        path = LOGO_DIR / f"{LOGO_BASE}{ext}"
        if path.exists():
            return path
    return None


def get_sidebar_logo_base64_data_uri() -> str | None:
    """
    Retorna a logo como data URI (data:image/...;base64,...) para uso em HTML <img src="...">.
    Útil na tela de login para tratar a logo como imagem centralizada dentro de um único bloco.
    """
    path = get_sidebar_logo_path()
    if not path or not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        suffix, "image/png"
    )
    try:
        b = path.read_bytes()
        b64 = base64.b64encode(b).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


def save_sidebar_logo(file_bytes: bytes, filename: str) -> Path:
    """
    Salva a logo no diretório uploads/logo/ com nome logo.<ext>.
    Remove outras extensões de logo existentes.
    """
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        ext = ".png"
    path = LOGO_DIR / f"{LOGO_BASE}{ext}"
    path.write_bytes(file_bytes)
    # Remove outras extensões para não deixar arquivos órfãos
    for e in ALLOWED_EXT:
        if e != ext:
            other = LOGO_DIR / f"{LOGO_BASE}{e}"
            if other.exists():
                other.unlink()
    return path


def remove_sidebar_logo() -> bool:
    """Remove a logo do sidebar (qualquer extensão). Retorna True se removeu algum arquivo."""
    removed = False
    if LOGO_DIR.exists():
        for ext in ALLOWED_EXT:
            path = LOGO_DIR / f"{LOGO_BASE}{ext}"
            if path.exists():
                path.unlink()
                removed = True
    return removed
