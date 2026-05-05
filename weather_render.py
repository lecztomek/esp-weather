from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta

OUT = Path("public")
OUT.mkdir(exist_ok=True)

W, H = 240, 240

HOURS = ["00", "03", "06", "09", "12", "15", "18", "21"]


def load_font(size, bold=False):
    candidates = []

    if bold:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]

    candidates += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


font_title = load_font(25, bold=True)
font_small = load_font(10)
font_axis = load_font(10)
font_temp = load_font(12, bold=True)
font_mm = load_font(10)


def text_center(draw, box, text, font, fill):
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = x0 + (x1 - x0 - tw) // 2
    y = y0 + (y1 - y0 - th) // 2 - 1
    draw.text((x, y), text, font=font, fill=fill)


def draw_polyline(draw, points, fill, width=2):
    if len(points) < 2:
        return

    for i in range(len(points) - 1):
        draw.line((points[i], points[i + 1]), fill=fill, width=width)


def draw_icon_sun(draw, cx, cy):
    color = (255, 205, 55)
    ray = (255, 220, 90)

    for dx, dy in [
        (0, -18), (0, 18), (-18, 0), (18, 0),
        (-13, -13), (13, -13), (-13, 13), (13, 13),
    ]:
        draw.line((cx, cy, cx + dx, cy + dy), fill=ray, width=3)

    draw.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill=color, outline=(245, 180, 40), width=2)


def draw_icon_cloud(draw, cx, cy):
    fill = (230, 236, 245)
    outline = (160, 175, 195)

    draw.ellipse((cx - 19, cy - 2, cx + 1, cy + 18), fill=fill, outline=outline, width=2)
    draw.ellipse((cx - 6, cy - 12, cx + 18, cy + 14), fill=fill, outline=outline, width=2)
    draw.ellipse((cx + 8, cy - 2, cx + 28, cy + 18), fill=fill, outline=outline, width=2)
    draw.rounded_rectangle((cx - 20, cy + 5, cx + 30, cy + 20), radius=7, fill=fill, outline=outline, width=2)


def draw_icon_partly(draw, cx, cy):
    draw_icon_sun(draw, cx - 8, cy - 5)

    # Chmurka na wierzchu
    fill = (235, 240, 248)
    outline = (160, 175, 195)

    draw.ellipse((cx - 17, cy + 0, cx + 1, cy + 18), fill=fill, outline=outline, width=2)
    draw.ellipse((cx - 5, cy - 8, cx + 17, cy + 15), fill=fill, outline=outline, width=2)
    draw.ellipse((cx + 9, cy + 1, cx + 27, cy + 18), fill=fill, outline=outline, width=2)
    draw.rounded_rectangle((cx - 18, cy + 7, cx + 29, cy + 21), radius=7, fill=fill, outline=outline, width=2)


def draw_icon_rain(draw, cx, cy):
    draw_icon_cloud(draw, cx, cy - 5)

    blue = (45, 135, 215)

    for x in [cx - 12, cx, cx + 12]:
        draw.line((x, cy + 22, x - 4, cy + 32), fill=blue, width=3)


def draw_icon_snow(draw, cx, cy):
    draw_icon_cloud(draw, cx, cy - 5)

    blue = (80, 160, 220)

    for x in [cx - 12, cx, cx + 12]:
        y = cy + 27
        draw.line((x - 4, y, x + 4, y), fill=blue, width=2)
        draw.line((x, y - 4, x, y + 4), fill=blue, width=2)


def draw_weather_icon(draw, weather, cx, cy):
    if weather == "sun":
        draw_icon_sun(draw, cx, cy)
    elif weather == "partly":
        draw_icon_partly(draw, cx, cy)
    elif weather == "rain":
        draw_icon_rain(draw, cx, cy)
    elif weather == "snow":
        draw_icon_snow(draw, cx, cy)
    else:
        draw_icon_cloud(draw, cx, cy)


def make_test_day(day_offset):
    if day_offset == 0:
        temps = [-1, -2, -1, 2, 5, 4, 2, 1]
        rain = [0, 0, 0, 0, 0, 1, 2, 1]
        weather = "partly"
        title = "DZISIAJ"
    elif day_offset == 1:
        temps = [1, 0, 0, 3, 6, 5, 3, 2]
        rain = [0, 0, 0, 0, 0, 0, 1, 2]
        weather = "sun"
        title = "JUTRO"
    else:
        temps = [0, -1, -1, 1, 3, 2, 1, 0]
        rain = [0, 0, 1, 2, 3, 2, 1, 0]
        weather = "rain"
        title = "POJUTRZE"

    return {
        "filename": f"screen_{day_offset}.png",
        "title": title,
        "temps": temps,
        "rain": rain,
        "weather": weather,
    }


def draw_temperature_chart(draw, temps, x0, y0, x1, y1):
    min_t = min(temps)
    max_t = max(temps)

    if min_t == max_t:
        min_t -= 1
        max_t += 1

    min_t -= 1
    max_t += 1

    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=8,
        fill=(246, 249, 253),
        outline=(220, 228, 238),
    )

    for i in range(1, 3):
        gy = y0 + i * (y1 - y0) // 3
        draw.line((x0 + 5, gy, x1 - 5, gy), fill=(228, 234, 242), width=1)

    points = []
    n = len(temps)

    for i, temp in enumerate(temps):
        x = x0 + 10 + i * ((x1 - x0 - 20) / (n - 1))
        ratio = (temp - min_t) / (max_t - min_t)
        y = y1 - 8 - ratio * (y1 - y0 - 16)
        points.append((int(x), int(y)))

    draw_polyline(draw, points, fill=(230, 100, 35), width=3)

    for x, y in points:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(230, 100, 35))

    draw.text((x0 + 6, y0 + 3), f"{max(temps)}°", font=font_small, fill=(120, 130, 145))
    draw.text((x0 + 6, y1 - 14), f"{min(temps)}°", font=font_small, fill=(120, 130, 145))


def draw_rain_bars(draw, rain, x0, y0, x1, y1):
    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=8,
        fill=(246, 249, 253),
        outline=(220, 228, 238),
    )

    max_rain = max(max(rain), 1)

    n = len(rain)
    usable_w = x1 - x0 - 16
    gap = 3
    bar_w = max(4, int((usable_w - gap * (n - 1)) / n))

    base_y = y1 - 17
    top_y = y0 + 8
    chart_h = base_y - top_y

    for i, mm in enumerate(rain):
        bx = x0 + 8 + i * (bar_w + gap)
        bh = int((mm / max_rain) * chart_h)
        by = base_y - bh

        if mm > 0:
            draw.rounded_rectangle(
                (bx, by, bx + bar_w, base_y),
                radius=2,
                fill=(40, 130, 210),
            )
        else:
            draw.line((bx, base_y, bx + bar_w, base_y), fill=(190, 205, 220), width=1)

        label = str(mm)
        bbox = draw.textbbox((0, 0), label, font=font_mm)
        tw = bbox[2] - bbox[0]
        draw.text((bx + (bar_w - tw) // 2, y1 - 14), label, font=font_mm, fill=(70, 100, 130))

    draw.text((x0 + 6, y0 + 3), "opad mm", font=font_small, fill=(70, 100, 130))


def draw_screen(data):
    img = Image.new("RGB", (W, H), (235, 241, 248))
    d = ImageDraw.Draw(img)

    # Główna karta
    d.rounded_rectangle(
        (5, 5, 235, 235),
        radius=18,
        fill=(255, 255, 255),
        outline=(210, 220, 232),
    )

    # Header
    d.rounded_rectangle(
        (9, 9, 231, 50),
        radius=14,
        fill=(36, 84, 150),
    )

    # Ikona rysowana kształtami, nie emoji
    draw_weather_icon(d, data["weather"], 35, 27)

    # Tytuł
    title = data["title"]
    bbox = d.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    d.text((136 - tw // 2, 16), title, font=font_title, fill=(255, 255, 255))

    # Sekcja godzin i temperatur
    x0, x1 = 11, 229
    y_hours = 61
    y_temps = 81
    col_w = (x1 - x0) / len(HOURS)

    for i, hour in enumerate(HOURS):
        cx = int(x0 + col_w * i + col_w / 2)

        text_center(
            d,
            (cx - 13, y_hours, cx + 13, y_hours + 13),
            hour,
            font_axis,
            (80, 90, 105),
        )

        temp = f'{data["temps"][i]}°'
        text_center(
            d,
            (cx - 14, y_temps, cx + 14, y_temps + 16),
            temp,
            font_temp,
            (20, 30, 45),
        )

    d.line((13, 104, 227, 104), fill=(225, 232, 240), width=1)

    # Wykres temperatury
    draw_temperature_chart(d, data["temps"], 12, 111, 228, 164)

    # Słupki opadów
    draw_rain_bars(d, data["rain"], 12, 172, 228, 224)

    # Zapis
    png_path = OUT / data["filename"]
    jpg_path = OUT / data["filename"].replace(".png", ".jpg")

    img.save(png_path, "PNG")
    img.convert("RGB").save(jpg_path, "JPEG", quality=92)


def write_index():
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>ESP Weather Screens</title>
  <style>
    body {{
      font-family: system-ui, sans-serif;
      background: #eef2f7;
      padding: 24px;
      color: #1f2937;
    }}
    .screens {{
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .card {{
      background: white;
      padding: 14px;
      border-radius: 16px;
      box-shadow: 0 4px 20px #0001;
    }}
    img {{
      width: 240px;
      height: 240px;
      image-rendering: auto;
      border-radius: 12px;
    }}
    code {{
      background: #f2f2f2;
      padding: 2px 6px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <h1>ESP Weather Screens</h1>
  <p>Wygenerowano: <strong>{generated}</strong></p>

  <div class="screens">
    <div class="card">
      <h3>Dzisiaj</h3>
      <img src="screen_0.png">
      <p><code>screen_0.png</code></p>
    </div>

    <div class="card">
      <h3>Jutro</h3>
      <img src="screen_1.png">
      <p><code>screen_1.png</code></p>
    </div>

    <div class="card">
      <h3>Pojutrze</h3>
      <img src="screen_2.png">
      <p><code>screen_2.png</code></p>
    </div>
  </div>
</body>
</html>
"""

    (OUT / "index.html").write_text(html, encoding="utf-8")


def main():
    for day_offset in range(3):
        draw_screen(make_test_day(day_offset))

    write_index()
    print("Generated screens in public/")


if __name__ == "__main__":
    main()
