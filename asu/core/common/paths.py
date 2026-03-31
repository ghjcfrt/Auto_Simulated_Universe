import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(".").resolve()
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
IMGS_DIR = PROJECT_ROOT / "imgs"
MAPS_DIR = IMGS_DIR / "maps"
LOGS_DIR = PROJECT_ROOT / "logs"
ASSETS_MODELS_DIR = PROJECT_ROOT / "asu" / "assets" / "models"
ACTIONS_DIR = PROJECT_ROOT / "actions"


def _stringify_parts(parts) -> list[str]:
    return [str(part) for part in parts]


def project_path(*parts: str) -> str:
    return str(PROJECT_ROOT.joinpath(*_stringify_parts(parts)))


def img_path(*parts: str) -> str:
    return str(IMGS_DIR.joinpath(*_stringify_parts(parts)))


def maps_dir() -> str:
    return str(MAPS_DIR)


def maps_path(*parts: str) -> str:
    return str(MAPS_DIR.joinpath(*_stringify_parts(parts)))


def logs_path(*parts: str, use_cwd: bool = False) -> str:
    base_dir = Path.cwd() / "logs" if use_cwd else LOGS_DIR
    return str(base_dir.joinpath(*_stringify_parts(parts)))


def actions_path(*parts: str) -> str:
    return str(ACTIONS_DIR.joinpath(*_stringify_parts(parts)))


def models_path(*parts: str) -> str:
    return str(ASSETS_MODELS_DIR.joinpath(*_stringify_parts(parts)))
