import cv2 as cv
import numpy as np

# #57597e 是 RGB 格式
# 转成 BGR（OpenCV 用 BGR）
hex_color = "#57597e"
r = int(hex_color[1:3], 16)
g = int(hex_color[3:5], 16)
b = int(hex_color[5:7], 16)

print(f"RGB: ({r}, {g}, {b})")

# 转成 BGR
bgr = np.uint8([[[b, g, r]]])
hsv = cv.cvtColor(bgr, cv.COLOR_BGR2HSV)
h, s, v = hsv[0, 0]

print(f"BGR: ({b}, {g}, {r})")
print(f"HSV: H={h}, S={s}, V={v}")
print("\n用于 cv.inRange 的范围（加上容差）:")
print(f"下限: [{max(0, h - 5)}, {max(0, s - 30)}, {max(0, v - 30)}]")
print(f"上限: [{min(255, h + 5)}, {min(255, s + 30)}, {min(255, v + 30)}]")
