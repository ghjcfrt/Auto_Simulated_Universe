import pyautogui
from asu.core.diver.config import config
import time
import threading

def get_mapping(x):
    if x in config.origin_key:
        x = config.mapping[config.origin_key.index(x)]
    return x

def keyDown(x, pause=True):
    pyautogui.keyDown(get_mapping(x), _pause=pause)
def keyUp(x, pause=True):
    if config.long_press_sprint and x=='w':
        pyautogui.keyUp(get_mapping('shift'), _pause=pause)
    pyautogui.keyUp(get_mapping(x), _pause=pause)

class KeyController:
    def __init__(self, father):
        self.events = []
        self.fff = 0
        self.father = father
        threading.Thread(target=self.loop).start()

    def loop(self):
        while not self.father._stop:
            if self.fff:
                keyDown('f')
                time.sleep(0.02)
                keyUp('f')
            else:
                time.sleep(0.1)
            for event in self.events:
                if event['type']=='down':
                    keyDown(event['key'])
                elif event['type']=='up':
                    keyUp(event['key'])
