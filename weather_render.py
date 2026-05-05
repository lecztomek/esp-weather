from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, date
import requests

OUT = Path("public")
OUT.mkdir(exist_ok=True)

W, H = 240, 240

# Nowy Sącz mniej więcej
LATITUDE = 49.6175
LONGITUDE = 20.7153
TIMEZONE = "Europe/Warsaw"

HOURS_WANTED = ["00", "03", "06", "09", "12", "15", "18", "21"]

DAY_TITLES = ["DZISIAJ", "JUTRO", "POJUTRZE"]


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

    draw.ellipse(
        (cx - 11, cy - 11, cx + 11, cy + 11),
        fill=color,
        outline=(245, 180, 40),
        width=2,
    )


def draw_icon_cloud(draw, cx, cy):
    fill = (230, 236, 245)
    outline = (160, 175, 195)

    draw.ellipse((cx - 19, cy - 2, cx + 1, cy + 18), fill=fill, outline=outline, width=2)
    draw.ellipse((cx - 6, cy - 12, cx + 18, cy + 14), fill=fill, outline=outline, width=2)
    draw.ellipse((cx + 8, cy - 2, cx + 28, cy + 18), fill=fill, outline=outline, width=2)
    draw.rounded_rectangle((cx - 20, cy + 5, cx + 30, cy + 20), radius=7, fill=fill, outline=outline, width=2)


def draw_icon_partly(draw, cx, cy):
    draw_icon_sun(draw, cx - 8, cy - 5)

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
        draw.line((x - 3, y - 3, x + 3, y + 3), fill=blue, width=2)
        draw.line((x - 3, y + 3, x + 3, y - 3), fill=blue, width=2)


def draw_icon_storm(draw, cx, cy):
    draw_icon_cloud(draw, cx, cy - 6)

    yellow = (255, 205, 45)
    outline = (210, 150, 20)
    blue = (45, 135, 215)

    bolt = [
        (cx + 2, cy + 13),
        (cx - 8, cy + 29),
        (cx + 1, cy + 28),
        (cx - 5, cy + 43),
        (cx + 13, cy + 21),
        (cx + 4, cy + 22),
    ]

    draw.polygon(bolt, fill=yellow, outline=outline)

    for x in [cx - 16, cx + 18]:
        draw.line((x, cy + 23, x - 4, cy + 33), fill=blue, width=3)


def draw_icon_fog(draw, cx, cy):
    fog = (145, 160, 180)

    draw.line((cx - 26, cy - 12, cx + 26, cy - 12), fill=fog, width=4)
    draw.line((cx - 18, cy - 3,  cx + 20, cy - 3),  fill=fog, width=4)
    draw.line((cx - 26, cy + 6,  cx + 26, cy + 6),  fill=fog, width=4)
    draw.line((cx - 18, cy + 15, cx + 20, cy + 15), fill=fog, width=4)


def draw_icon_sleet(draw, cx, cy):
    draw_icon_cloud(draw, cx, cy - 6)

    blue = (45, 135, 215)
    ice = (80, 160, 220)

    for x in [cx - 13, cx + 13]:
        draw.line((x, cy + 22, x - 4, cy + 32), fill=blue, width=3)

    x = cx
    y = cy + 29
    draw.line((x - 4, y, x + 4, y), fill=ice, width=2)
    draw.line((x, y - 4, x, y + 4), fill=ice, width=2)
    draw.line((x - 3, y - 3, x + 3, y + 3), fill=ice, width=2)
    draw.line((x - 3, y + 3, x + 3, y - 3), fill=ice, width=2)


def draw_weather_icon(draw, weather, cx, cy):
    if weather == "sun":
        draw_icon_sun(draw, cx, cy)
    elif weather == "partly":
        draw_icon_partly(draw, cx, cy)
    elif weather == "cloud":
        draw_icon_cloud(draw, cx, cy)
    elif weather == "rain":
        draw_icon_rain(draw, cx, cy)
    elif weather == "snow":
        draw_icon_snow(draw, cx, cy)
    elif weather == "storm":
        draw_icon_storm(draw, cx, cy)
    elif weather == "fog":
        draw_icon_fog(draw, cx, cy)
    elif weather == "sleet":
        draw_icon_sleet(draw, cx, cy)
    else:
        draw_icon_cloud(draw, cx, cy)


def map_weather_code(code):
    # Open-Meteo WMO weather codes:
    # 0 clear
    # 1,2 partly cloudy
    # 3 overcast
    # 45,48 fog
    # 51-67 drizzle/rain/freezing rain
    # 71-86 snow
    # 95-99 thunderstorm

    if code == 0:
        return "sun"

    if code in [1, 2]:
        return "partly"

    if code == 3:
        return "cloud"

    if code in [45, 48]:
        return "fog"

    if code in [56, 57, 66, 67]:
        return "sleet"

    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "rain"

    if code in [71, 73, 75, 77, 85, 86]:
        return "snow"

    if code in [95, 96, 99]:
        return "storm"

    return "cloud"


def fetch_open_meteo():
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,precipitation,weather_code",
        "forecast_days": 3,
        "timezone": TIMEZONE,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def pick_day_weather_icon(codes):
    priority = [
        "storm",
        "snow",
        "sleet",
        "rain",
        "fog",
        "cloud",
        "partly",
        "sun",
    ]

    mapped = [map_weather_code(code) for code in codes]

    for icon in priority:
        if icon in mapped:
            return icon

    return "cloud"


def build_screens_from_forecast(data):
    hourly = data["hourly"]

    times = hourly["time"]
    temperatures = hourly["temperature_2m"]
    precipitation = hourly["precipitation"]
    weather_codes = hourly["weather_code"]

    by_day = {}

    for t, temp, rain, code in zip(times, temperatures, precipitation, weather_codes):
        # Format z Open-Meteo: YYYY-MM-DDTHH:MM
        day_str = t[:10]
        hour_str = t[11:13]

        if hour_str not in HOURS_WANTED:
            continue

        by_day.setdefault(day_str, []).append(
            {
                "hour": hour_str,
                "temp": temp,
                "rain": rain,
                "code": code,
            }
        )

    days = sorted(by_day.keys())[:3]
    screens = []

    for idx, day_str in enumerate(days):
        rows = sorted(by_day[day_str], key=lambda x: x["hour"])

        # Gdyby API z jakiegoś powodu nie dało kompletu godzin, uzupełniamy bez crasha.
        row_by_hour = {r["hour"]: r for r in rows}
        final_rows = []

        for hour in HOURS_WANTED:
            if hour in row_by_hour:
                final_rows.append(row_by_hour[hour])

        temps = [int(round(r["temp"])) for r in final_rows]
        rain = [int(round(r["rain"])) for r in final_rows]
        codes = [int(r["code"]) for r in final_rows]

        if not temps:
            continue

        title = DAY_TITLES[idx] if idx < len(DAY_TITLES) else day_str

        screens.append(
            {
                "filename": f"screen_{idx}.png",
                "title": title,
                "weather": pick_day_weather_icon(codes),
                "temps": temps,
                "rain": rain,
                "hours": [r["hour"] for r in final_rows],
                "source_date": day_str,
            }
        )

    return screens


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
        x = x0 + 10 + i * ((x1 - x0 - 20) / max(n - 1, 1))
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

    hours = data.get("hours", HOURS_WANTED)

    d.rounded_rectangle(
        (5, 5, 235, 235),
        radius=18,
        fill=(255, 255, 255),
        outline=(210, 220, 232),
    )

    d.rounded_rectangle(
        (9, 9, 231, 50),
        radius=14,
        fill=(36, 84, 150),
    )

    draw_weather_icon(d, data["weather"], 35, 27)

    title = data["title"]
    bbox = d.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]

    d.text((138 - tw // 2, 16), title, font=font_title, fill=(255, 255, 255))

    x0, x1 = 11, 229
    y_hours = 61
    y_temps = 81
    col_w = (x1 - x0) / len(hours)

    for i, hour in enumerate(hours):
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

    draw_temperature_chart(d, data["temps"], 12, 111, 228, 164)
    draw_rain_bars(d, data["rain"], 12, 172, 228, 224)

    png_path = OUT / data["filename"]
    jpg_path = OUT / data["filename"].replace(".png", ".jpg")

    img.save(png_path, "PNG")
    img.convert("RGB").save(jpg_path, "JPEG", quality=92)


def write_index(screens, source_info):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    cards = []

    for screen in screens:
        title = screen["title"]
        filename = screen["filename"]
        weather = screen["weather"]
        source_date = screen.get("source_date", "")

        cards.append(
            f"""
    <div class="card">
      <h3>{title}</h3>
      <img src="{filename}">
      <p><code>{filename}</code></p>
      <p class="muted">ikona: <code>{weather}</code></p>
      <p class="muted">data prognozy: <code>{source_date}</code></p>
    </div>
"""
        )

    cards_html = "\n".join(cards)

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
    .muted {{
      color: #6b7280;
      margin-top: -4px;
    }}
  </style>
</head>
<body>
  <h1>ESP Weather Screens</h1>
  <p>Wygenerowano: <strong>{generated}</strong></p>
  <p class="muted">{source_info}</p>

  <div class="screens">
{cards_html}
  </div>
</body>
</html>
"""

    (OUT / "index.html").write_text(html, encoding="utf-8")


def main():
    forecast = fetch_open_meteo()
    screens = build_screens_from_forecast(forecast)

    if not screens:
        raise RuntimeError("Nie udało się zbudować żadnego ekranu z danych pogodowych")

    for screen in screens:
        draw_screen(screen)

    source_info = f"Źródło: Open-Meteo, lat={LATITUDE}, lon={LONGITUDE}, timezone={TIMEZONE}"
    write_index(screens, source_info)

    print("Generated real weather screens in public/")


if __name__ == "__main__":
    main()
