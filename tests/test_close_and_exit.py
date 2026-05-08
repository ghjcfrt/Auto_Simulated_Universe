import time

# 请求管理员权限
import pyuac

if not pyuac.isUserAdmin():
    print("此脚本需要管理员权限运行")
    pyuac.runAsAdmin()
else:
    print("请在 5 秒内切到目标窗口（游戏/程序）...")
    time.sleep(5)

    # =========================
    # 1️⃣ keyboard
    # =========================
    try:
        import keyboard

        print("[TEST] keyboard ESC")
        keyboard.press("esc")
        time.sleep(1)
        keyboard.release("esc")
        time.sleep(2)
    except Exception as e:
        print("keyboard 失败:", e)

    # =========================
    # 2️⃣ pyautogui
    # =========================
    try:
        import pyautogui

        print("[TEST] pyautogui ESC")
        pyautogui.keyDown("esc")
        time.sleep(1)
        pyautogui.keyUp("esc")
        time.sleep(2)
    except Exception as e:
        print("pyautogui 失败:", e)

    # =========================
    # 3️⃣ win32api
    # =========================
    try:
        import win32api
        import win32con

        print("[TEST] win32api ESC")
        win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
        time.sleep(1)
        win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(2)
    except Exception as e:
        print("win32api 失败:", e)

    print("测试完成")
