from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

OUT = Path("public")
OUT.mkdir(exist_ok=True)

W, H = 240, 240

screens = [
    {
        "filename": "screen_0.png",
        "title": "DZISIAJ",
        "date": "Dzisiaj",
        "hours": [
            ("09:00", "2°C", "0 mm", "☁"),
            ("12:00", "5°C", "0 mm", "⛅"),
            ("15:00", "4°C", "1 mm", "🌧"),
            ("18:00", "1°C", "0 mm", "☁"),
        ],
    },
    {
        "filename": "screen_1.png",
        "title": "JUTRO",
        "date": "Jutro",
        "hours": [
            ("09:00", "3°C", "0 mm", "⛅"),
            ("12:00", "6°C", "0 mm", "☀"),
            ("15:00", "5°C", "0 mm", "⛅"),
            ("18:00", "2°C", "1 mm", "🌧"),
        ],
    },
    {
        "filename": "screen_2.png",
        "title": "POJUTRZE",
        "date": "Pojutrze",
        "hours": [
            ("09:00", "1°C", "0 mm", "☁"),
            ("12:00", "4°C", "0 mm", "⛅"),
            ("15:00", "3°C", "2 mm", "🌧"),
            ("18:00", "0°C", "0 mm", "☁"),
        ],
    },
]

def load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

font_title = load_font(26)
font_sub = load_font(13)
font_hour = load_font(15)
font_temp = load_font(18)
font_small = load_font(12)
font_icon = load_font(25)

def draw_screen(data):
    img = Image.new("RGB", (W, H), (245, 248, 252))
    d = ImageDraw.Draw(img)

    # Header
    d.rounded_rectangle((8, 8, 232, 48), radius=14, fill=(40, 90, 160))
    d.text((18, 13), data["title"], font=font_title, fill=(255, 255, 255))
    d.text((156, 26), data["date"], font=font_sub, fill=(220, 235, 255))

    # Card area
    d.rounded_rectangle((8, 58, 232, 224), radius=16, fill=(255, 255, 255), outline=(220, 226, 235))

    col_w = 224 // 4

    for i, item in enumerate(data["hours"]):
        hour, temp, rain, icon = item
        x0 = 8 + i * col_w
        x1 = x0 + col_w

        if i > 0:
            d.line((x0, 72, x0, 210), fill=(230, 234, 240), width=1)

        # Hour
        bbox = d.textbbox((0, 0), hour, font=font_hour)
        tw = bbox[2] - bbox[0]
        d.text((x0 + (col_w - tw) // 2, 74), hour, font=font_hour, fill=(50, 60, 75))

        # Icon
        bbox = d.textbbox((0, 0), icon, font=font_icon)
        tw = bbox[2] - bbox[0]
        d.text((x0 + (col_w - tw) // 2, 102), icon, font=font_icon, fill=(20, 30, 40))

        # Temperature
        bbox = d.textbbox((0, 0), temp, font=font_temp)
        tw = bbox[2] - bbox[0]
        d.text((x0 + (col_w - tw) // 2, 143), temp, font=font_temp, fill=(20, 30, 40))

        # Rain
        bbox = d.textbbox((0, 0), rain, font=font_small)
        tw = bbox[2] - bbox[0]
        d.text((x0 + (col_w - tw) // 2, 176), rain, font=font_small, fill=(50, 120, 190))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    d.text((12, 226), f"update: {generated}", font=font_small, fill=(120, 130, 145))

    img.save(OUT / data["filename"], "PNG")
    img.convert("RGB").save(OUT / data["filename"].replace(".png", ".jpg"), "JPEG", quality=90)

for s in screens:
    draw_screen(s)

# Prosta strona podglądu
html = """<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>ESP Weather Screens</title>
  <style>
    body { font-family: sans-serif; background: #eef2f7; padding: 24px; }
    .screens { display: flex; gap: 20px; flex-wrap: wrap; }
    .card { background: white; padding: 14px; border-radius: 16px; box-shadow: 0 4px 20px #0001; }
    img { width: 240px; height: 240px; image-rendering: auto; border-radius: 12px; }
    code { background: #f2f2f2; padding: 2px 6px; border-radius: 6px; }
  </style>
</head>
<body>
  <h1>ESP Weather Screens</h1>
  <p>Podgląd ekranów 240x240.</p>
  <div class="screens">
    <div class="card"><h3>Dzisiaj</h3><img src="screen_0.png"><p><code>screen_0.png</code></p></div>
    <div class="card"><h3>Jutro</h3><img src="screen_1.png"><p><code>screen_1.png</code></p></div>
    <div class="card"><h3>Pojutrze</h3><img src="screen_2.png"><p><code>screen_2.png</code></p></div>
  </div>
</body>
</html>
"""

(OUT / "index.html").write_text(html, encoding="utf-8")

print("Generated screens in public/")
