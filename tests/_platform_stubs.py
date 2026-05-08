import sys
import types


def _register(name: str, module: types.ModuleType) -> types.ModuleType:
    sys.modules[name] = module
    return module


def install_platform_stubs() -> None:
    """在缺少平台依赖时注入最小桩模块，保证单元测试可运行。"""
    if "pythoncom" not in sys.modules:
        pythoncom = types.ModuleType("pythoncom")
        pythoncom.CoInitialize = lambda: None
        _register("pythoncom", pythoncom)

    if "win32com.client" not in sys.modules:
        client = types.ModuleType("win32com.client")

        class _Shell:
            def SendKeys(self, *_args, **_kwargs):
                return None

        client.Dispatch = lambda _name: _Shell()
        _register("win32com.client", client)

        win32com = sys.modules.get("win32com")
        if win32com is None:
            win32com = _register("win32com", types.ModuleType("win32com"))
        win32com.client = client

    if "win32gui" not in sys.modules:
        win32gui = types.ModuleType("win32gui")
        win32gui.FindWindow = lambda *_args, **_kwargs: 0
        win32gui.SetForegroundWindow = lambda *_args, **_kwargs: None
        win32gui.GetForegroundWindow = lambda: 0
        win32gui.GetWindowText = lambda _hwnd: ""
        win32gui.GetClientRect = lambda _hwnd: (0, 0, 1920, 1080)
        win32gui.GetWindowRect = lambda _hwnd: (0, 0, 1920, 1080)
        win32gui.GetWindowDC = lambda _hwnd: 1
        win32gui.ReleaseDC = lambda *_args, **_kwargs: None
        _register("win32gui", win32gui)

    if "win32con" not in sys.modules:
        win32con = types.ModuleType("win32con")
        win32con.LOGPIXELSX = 88
        win32con.LOGPIXELSY = 90
        _register("win32con", win32con)

    if "win32print" not in sys.modules:
        win32print = types.ModuleType("win32print")
        win32print.GetDeviceCaps = lambda *_args, **_kwargs: 96
        _register("win32print", win32print)

    if "win32api" not in sys.modules:
        win32api = types.ModuleType("win32api")
        win32api.SetCursorPos = lambda *_args, **_kwargs: None
        _register("win32api", win32api)

    if "pyautogui" not in sys.modules:
        pyautogui = types.ModuleType("pyautogui")
        setattr(pyautogui, "click", lambda *_args, **_kwargs: None)
        setattr(pyautogui, "drag", lambda *_args, **_kwargs: None)
        setattr(pyautogui, "keyDown", lambda *_args, **_kwargs: None)
        setattr(pyautogui, "keyUp", lambda *_args, **_kwargs: None)
        setattr(pyautogui, "screenshot", lambda: None)
        _register("pyautogui", pyautogui)

    if "cv2" not in sys.modules:
        cv2 = types.ModuleType("cv2")
        cv2.COLOR_BGR2RGB = 0
        cv2.TM_CCOEFF_NORMED = 0
        cv2.cvtColor = lambda image, _code: image
        cv2.matchTemplate = lambda *_args, **_kwargs: [[0]]
        cv2.minMaxLoc = lambda _res: (0, 0, (0, 0), (0, 0))
        _register("cv2", cv2)
