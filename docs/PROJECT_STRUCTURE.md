# Project Structure

## Goals
- Keep entry commands simple and obvious.
- Make source layout readable at a glance.
- Separate app orchestration, domain logic, UI, OCR, and assets.

## Current Layout
- `diver.py` / `simul.py` / `gui.py` / `align_angle.py` / `notif.py`: thin compatibility entry files.
- `asu/apps/`: thin compatibility entry modules.
- `asu/workflows/`: large workflow implementations (`diver`, `simul`).
- `asu/core/common/`: shared runtime, window state, and interaction helpers.
- `asu/core/diver/`: 差分宇宙 domain logic and configuration.
- `asu/core/simul/`: 模拟宇宙 domain logic and configuration.
- `asu/core/platform/`: platform-facing helpers (`log.py`, `screenshot.py`).
- `asu/ui/`: GUI layer (Flet views and page helpers).
- `asu/onnxocr/`: third-party OCR boundary.
- `asu/assets/models/`: OCR model assets.
- `actions/`, `imgs/`: runtime action tables and image assets.

## Rules For New Code
- Put new large flow implementations in `asu/workflows/`, and keep `asu/apps/` thin.
- Keep repository-root python files as wrappers only.
- Keep reusable core logic under `asu/core/`.
- Keep UI code in `asu/ui/` and avoid mixing business logic into UI modules.
- Keep OCR vendor code inside `asu/onnxocr/` and business logic outside of it.
- Keep large constant tables in dedicated `constants.py` files in each domain package.
