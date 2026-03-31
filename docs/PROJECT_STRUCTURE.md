# Project Structure

## Goals
- Keep the original CLI commands unchanged.
- Move large app entry scripts out of the repository root.
- Make future module extraction easier.

## Current Layout
- `diver.py` / `simul.py` / `abyss.py` / `gui.py` / `align_angle.py` / `notif.py`: compatibility entry files.
- `asu/apps/`: real application entry modules.
- `utils/`: shared automation, OCR, GUI helper, and config modules.
- `utils/onnxocr/`: third-party OCR code boundary (marked by `THIRD_PARTY.md` and `.third_party`).
- `utils/common/runtime.py`: shared runtime functions (`notif`, `set_forground`).
- `utils/common/window.py`: shared game-window initialization logic.
- `utils/common/interaction.py`: shared coordinate and mouse interaction helpers.
- `actions/`, `imgs/`, `utils/models/`: runtime assets and model files.
- `utils/diver/constants.py` / `utils/simul/constants.py`: extracted config constants and defaults.

## Rules For New Code
- Put new top-level app flows in `asu/apps/`.
- Keep repository-root python files as thin wrappers only.
- Put reusable business logic under `utils/` subpackages.
- Keep large static tables and default configs in dedicated `constants.py` modules.
- Keep `utils/onnxocr/` as third-party code; avoid mixing product logic into this directory.
