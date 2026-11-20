"""Regenerates fixtures/sample-handwritten-bill.png (needs Pillow). Fictional, anonymised data.
The bill deliberately contains a wrong line total, a smudged quantity and no tax line so the
review step has something to catch."""
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

random.seed(7)
W, H = 900, 1150
img = Image.new("RGB", (W, H), (250, 246, 232))
d = ImageDraw.Draw(img)
for y in range(150, H - 60, 52):
    d.line([(40, y), (W - 40, y)], fill=(196, 208, 222), width=2)
d.line([(110, 120), (110, H - 60)], fill=(226, 170, 170), width=2)


def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def hand(x, y, text, size=34, ink=(28, 40, 110)):
    f = font(size)
    for ch in text:
        layer = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((size // 2, size // 3), ch, font=f, fill=ink + (235,))
        layer = layer.rotate(random.uniform(-7, 7), resample=Image.BICUBIC)
        img.paste(layer, (int(x - size // 2), int(y - size // 3 + random.uniform(-3, 3))), layer)
        x += f.getlength(ch) + random.uniform(-1, 2)


hand(250, 40, "SRI LAKSHMI TRADERS", 40)
hand(300, 92, "Cash / Credit Bill", 26)
hand(130, 160, "To:  Murugan Stores", 36)
hand(600, 160, sys.argv[1] if len(sys.argv) > 1 else "Date: 20/11", 30)
hand(130, 264, "Item", 28)
hand(470, 264, "Qty", 28)
hand(570, 264, "Rate", 28)
hand(720, 264, "Amt", 28)
rows = [("Ponni rice 25kg bag", "2", "1200", "2400"), ("Toor dal 1kg", "5", "160", "850"), ("Sugar 50kg bag", "", "2100", "")]
for i, (item, qty, rate, amt) in enumerate(rows):
    y = 316 + i * 104
    hand(130, y, item, 32)
    hand(480, y, qty, 32)
    hand(570, y, rate, 32)
    hand(720, y, amt, 32)
d.ellipse([462, 520, 520, 566], fill=(70, 80, 130))  # ink smudge over the sugar quantity
d.line([(560, 660), (840, 660)], fill=(28, 40, 110), width=3)
hand(480, 680, "Total  Rs. 5350", 38)
hand(130, 800, "Balance later pls.", 30)
hand(560, 990, "Signature", 26)
img = img.filter(ImageFilter.GaussianBlur(0.6)).rotate(-1.2, resample=Image.BICUBIC, fillcolor=(232, 228, 214))
img.save("fixtures/sample-handwritten-bill.png", optimize=True)
