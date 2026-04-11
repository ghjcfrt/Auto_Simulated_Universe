import ctypes
import time
from ctypes import Structure
from ctypes.wintypes import DWORD, LONG, RECT, WORD
from threading import Lock

import numpy as np

from asu.core.platform.log import log


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize", DWORD),
        ("biWidth", LONG),
        ("biHeight", LONG),
        ("biPlanes", WORD),
        ("biBitCount", WORD),
        ("biCompression", DWORD),
        ("biSizeImage", DWORD),
        ("biXPelsPerMeter", LONG),
        ("biYPelsPerMeter", LONG),
        ("biClrUsed", DWORD),
        ("biClrImportant", DWORD),
    ]


class BITMAPINFO(Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


lock = Lock()


class Screen:
    def __init__(self, w=1920, h=1080):
        self.width, self.height = w, h
        self.user32 = ctypes.WinDLL("user32")
        self.gdi = ctypes.WinDLL("gdi32")

    def _ensure_bitmap(self, width, height):
        if width == self.width and height == self.height and hasattr(self, "bmi"):
            return
        self.width, self.height = width, height
        self.bmi = BITMAPINFO()
        self.bmi.bmiHeader.biSize = 40
        self.bmi.bmiHeader.biPlanes = 1
        self.bmi.bmiHeader.biBitCount = 32
        self.bmi.bmiHeader.biCompression = 0
        self.bmi.bmiHeader.biClrUsed = 0
        self.bmi.bmiHeader.biClrImportant = 0
        self.bmi.bmiHeader.biWidth = self.width
        self.bmi.bmiHeader.biHeight = -self.height
        self.data = ctypes.create_string_buffer(self.width * self.height * 4)

    def grab(self, hwnd):
        with lock:
            for _ in range(10):
                client_rect = RECT()
                if not self.user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
                    log.info("截图失败！")
                    time.sleep(0.05)
                    continue

                width = client_rect.right - client_rect.left
                height = client_rect.bottom - client_rect.top
                if width <= 0 or height <= 0:
                    log.info("截图失败！")
                    time.sleep(0.05)
                    continue

                self._ensure_bitmap(width, height)

                hwnd_dc = None
                mfc_dc = None
                save_dc = None
                save_bit_map = None

                try:
                    hwnd_dc = self.user32.GetWindowDC(hwnd)
                    if not hwnd_dc:
                        log.info("截图失败！")
                        time.sleep(0.05)
                        continue

                    import win32ui

                    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
                    save_dc = mfc_dc.CreateCompatibleDC()

                    save_bit_map = win32ui.CreateBitmap()
                    save_bit_map.CreateCompatibleBitmap(mfc_dc, width, height)
                    save_dc.SelectObject(save_bit_map)

                    flags = 1 | 2
                    result = self.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), flags)
                    if result == 0:
                        log.info("截图失败！")
                        time.sleep(0.05)
                        continue

                    bmp_info = save_bit_map.GetInfo()
                    bmp_data = save_bit_map.GetBitmapBits(True)
                    img = np.frombuffer(bytearray(bmp_data), dtype=np.uint8).reshape(
                        (bmp_info["bmHeight"], bmp_info["bmWidth"], 4)
                    )[:, :, :3]
                    return img
                finally:
                    if save_bit_map:
                        try:
                            self.gdi.DeleteObject(save_bit_map.GetHandle())
                        except Exception:
                            pass
                    if save_dc:
                        try:
                            save_dc.DeleteDC()
                        except Exception:
                            pass
                    if mfc_dc:
                        try:
                            mfc_dc.DeleteDC()
                        except Exception:
                            pass
                    if hwnd_dc:
                        try:
                            self.user32.ReleaseDC(hwnd, hwnd_dc)
                        except Exception:
                            pass
        return np.zeros((self.height, self.width, 4))
