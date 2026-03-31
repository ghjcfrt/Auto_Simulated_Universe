# 项目结构

## 目标
- 保持入口命令简单直观。
- 让源码目录一眼可读、职责清晰。
- 将应用编排、领域逻辑、UI、OCR 与资源文件分层管理。

## 当前布局
- `diver.py` / `simul.py` / `gui.py` / `align_angle.py` / `notif.py`：轻量兼容入口文件。
- `asu/apps/`：轻量兼容入口模块。
- `asu/workflows/`：主要流程实现（`diver`、`simul`）。
- `asu/core/common/`：共享运行时、窗口状态与交互辅助。
- `asu/core/diver/`：差分宇宙领域逻辑与配置。
- `asu/core/simul/`：模拟宇宙领域逻辑与配置。
- `asu/core/platform/`：平台相关辅助（`log.py`、`screenshot.py`）。
- `asu/ui/`：GUI 层（Flet 页面与通用界面辅助）。
- `asu/onnxocr/`：第三方 OCR 边界代码。
- `asu/assets/models/`：OCR 模型资源。
- `actions/`、`imgs/`：运行时动作表与图片资源。

## 新代码规则
- 新增的大型流程实现放在 `asu/workflows/`，`asu/apps/` 保持轻量。
- 仓库根目录下的 Python 文件仅作为包装入口。
- 可复用核心逻辑统一放在 `asu/core/`。
- UI 代码放在 `asu/ui/`，避免将业务逻辑混入 UI 模块。
- OCR 供应商代码保持在 `asu/onnxocr/` 内，业务逻辑放在其外部。
- 大型常量表放在各领域包专用的 `constants.py` 中。
