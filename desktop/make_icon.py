"""Draws desktop/app.ico (teal rounded square with a white medical cross). Run once; the .ico is committed."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, S - 8, S - 8), radius=56, fill=(15, 118, 110, 255))
arm, length = 44, 150
c = S // 2
d.rounded_rectangle((c - arm, c - length // 2, c + arm, c + length // 2), radius=12, fill="white")
d.rounded_rectangle((c - length // 2, c - arm, c + length // 2, c + arm), radius=12, fill="white")
out = Path(__file__).with_name("app.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)
