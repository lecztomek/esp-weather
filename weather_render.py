from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import requests

OUT = Path("public")
OUT.mkdir(exist_ok=True)

W, H = 240, 240

# Nowy Sącz mniej więcej
LATITUDE = 49.6175
LONGITUDE = 20.7153
TIMEZONE = "Europe/Warsaw"

HOURS_WANTED = ["00", "04", "08", "12", "16", "20"]

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
font_axis = load_font(12)
font_temp = load_font(14, bold=True)
font_extreme = load_font(15, bold=True)
font_mm = load_font(11, bold=True)


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


def draw_icon_sunrain(draw, cx, cy):
    draw_icon_sun(draw, cx - 9, cy - 7)

    fill = (235, 240, 248)
    outline = (160, 175, 195)

    draw.ellipse((cx - 17, cy + 0, cx + 1, cy + 18), fill=fill, outline=outline, width=2)
    draw.ellipse((cx - 5, cy - 8, cx + 17, cy + 15), fill=fill, outline=outline, width=2)
    draw.ellipse((cx + 9, cy + 1, cx + 27, cy + 18), fill=fill, outline=outline, width=2)
    draw.rounded_rectangle((cx - 18, cy + 7, cx + 29, cy + 21), radius=7, fill=fill, outline=outline, width=2)

    blue = (45, 135, 215)

    for x in [cx - 9, cx + 4, cx + 17]:
        draw.line((x, cy + 23, x - 4, cy + 33), fill=blue, width=3)


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
    draw.line((cx - 18, cy - 3, cx + 20, cy - 3), fill=fog, width=4)
    draw.line((cx - 26, cy + 6, cx + 26, cy + 6), fill=fog, width=4)
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
    elif weather == "sunrain":
        draw_icon_sunrain(draw, cx, cy)
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


def pick_day_weather_icon(codes, rain):
    mapped = [map_weather_code(code) for code in codes]

    if "storm" in mapped:
        return "storm"

    if "snow" in mapped:
        return "snow"

    if "sleet" in mapped:
        return "sleet"

    if "fog" in mapped:
        return "fog"

    sunny_slots = sum(1 for code in codes if code == 0)
    partly_slots = sum(1 for code in codes if code in [1, 2])
    cloudy_slots = sum(1 for code in codes if code == 3)

    rain_by_mm = any(mm >= 0.2 for mm in rain)
    rain_by_code = any(icon == "rain" for icon in mapped)

    has_rain = rain_by_mm or rain_by_code

    has_sun = sunny_slots + partly_slots >= 4
    mostly_cloudy = cloudy_slots > sunny_slots + partly_slots

    if has_rain:
        if has_sun and not mostly_cloudy:
            return "sunrain"

        return "rain"

    if sunny_slots >= 3:
        return "sun"

    if partly_slots >= 2:
        return "partly"

    return "cloud"


def build_screens_from_forecast(data):
    hourly = data["hourly"]

    times = hourly["time"]
    temperatures = hourly["temperature_2m"]
    precipitation = hourly["precipitation"]
    weather_codes = hourly["weather_code"]

    by_day = {}

    for t, temp, rain, code in zip(times, temperatures, precipitation, weather_codes):
        day_str = t[:10]
        hour = int(t[11:13])

        by_day.setdefault(day_str, []).append(
            {
                "hour": hour,
                "temp": temp,
                "rain": rain,
                "code": code,
            }
        )

    days = sorted(by_day.keys())[:3]
    screens = []

    wanted_hours_int = [int(h) for h in HOURS_WANTED]

    for idx, day_str in enumerate(days):
        rows = sorted(by_day[day_str], key=lambda x: x["hour"])

        if not rows:
            continue

        temps = []
        temps_min = []
        temps_max = []
        rain = []
        codes = []
        hours = []

        for i, start_hour in enumerate(wanted_hours_int):
            if i + 1 < len(wanted_hours_int):
                end_hour = wanted_hours_int[i + 1]
            else:
                end_hour = 24

            bucket = [
                r for r in rows
                if start_hour <= r["hour"] < end_hour
            ]

            if not bucket:
                continue

            bucket_temps = [float(r["temp"]) for r in bucket]

            temp_min = min(bucket_temps)
            temp_max = max(bucket_temps)
            temp_avg = sum(bucket_temps) / len(bucket_temps)

            rain_sum = sum(float(r["rain"] or 0) for r in bucket)
            bucket_codes = [int(r["code"]) for r in bucket]

            temps.append(int(round(temp_avg)))
            temps_min.append(int(round(temp_min)))
            temps_max.append(int(round(temp_max)))

            rain.append(round(rain_sum, 1))
            codes.extend(bucket_codes)
            hours.append(f"{start_hour:02d}")

        if not temps:
            continue

        title = DAY_TITLES[idx] if idx < len(DAY_TITLES) else day_str

        screens.append(
            {
                "filename": f"screen_{idx}.png",
                "title": title,
                "weather": pick_day_weather_icon(codes, rain),
                "temps": temps,
                "temps_min": temps_min,
                "temps_max": temps_max,
                "rain": rain,
                "hours": hours,
                "source_date": day_str,
                "codes": codes,
            }
        )

    return screens


def draw_temp_row(draw, values, x0, x1, y, color):
    n = len(values)
    col_w = (x1 - x0) / n

    for i, value in enumerate(values):
        cx = int(x0 + col_w * i + col_w / 2)

        text = f"{value}°"
        bbox = draw.textbbox((0, 0), text, font=font_extreme)
        tw = bbox[2] - bbox[0]

        draw.text(
            (cx - tw // 2, y),
            text,
            font=font_extreme,
            fill=color,
        )


def draw_combined_chart(draw, temps, temps_min, temps_max, rain, hours, x0, y0, x1, y1):
    all_temps = temps + temps_min + temps_max

    min_t = min(all_temps)
    max_t = max(all_temps)

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

    for i in range(1, 4):
        gy = y0 + i * (y1 - y0) // 4
        draw.line((x0 + 5, gy, x1 - 5, gy), fill=(228, 234, 242), width=1)

    n = len(temps)

    chart_left = x0 + 12
    chart_right = x1 - 12
    chart_top = y0 + 8
    chart_bottom = y1 - 10

    chart_w = chart_right - chart_left
    chart_h = chart_bottom - chart_top

    # Godziny: na wykresie, przy samej górze.
    for i, hour in enumerate(hours):
        cx = chart_left + i * (chart_w / max(n - 1, 1))

        text_center(
            draw,
            (int(cx - 13), y0 + 3, int(cx + 13), y0 + 17),
            hour,
            font_axis,
            (80, 90, 105),
        )

    # Miejsce pod godzinami, żeby linia temperatury ich nie dotykała.
    temp_top = chart_top + 18
    temp_bottom = chart_bottom
    temp_h = temp_bottom - temp_top

    # Opady: słupki zawsze od dolnej krawędzi wykresu.
    #
    # Skala:
    # - największy opad danego dnia ma wysokość rain_max_h,
    # - pozostałe słupki są proporcjonalne do niego,
    # - minimum 3 px tylko po to, żeby 0.1 mm było widoczne.
    max_rain = max(max(rain), 1)
    rain_max_h = int(temp_h * 0.55)

    gap = 5
    bar_w = max(6, int((chart_w - gap * (n - 1)) / n * 0.75))

    for i, mm in enumerate(rain):
        if mm <= 0:
            continue

        cx = chart_left + i * (chart_w / max(n - 1, 1))

        bx0 = int(cx - bar_w / 2)
        bx1 = int(cx + bar_w / 2)

        bh = int((mm / max_rain) * rain_max_h)
        bh = max(bh, 3)

        by1 = chart_bottom
        by0 = chart_bottom - bh

        draw.rounded_rectangle(
            (bx0, by0, bx1, by1),
            radius=2,
            fill=(70, 155, 225),
        )

        label = f"{mm:.1f}" if mm < 1 else f"{mm:.0f}"

        bbox = draw.textbbox((0, 0), label, font=font_mm)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # Czarny tekst przy dole słupka, ale lekko podniesiony.
        label_x = int(cx - tw / 2)
        label_y = chart_bottom - th - 5

        draw.text(
            (label_x, label_y),
            label,
            font=font_mm,
            fill=(20, 25, 30),
        )

    # Temperatura: linia średniej.
    points = []

    for i, temp in enumerate(temps):
        x = chart_left + i * (chart_w / max(n - 1, 1))
        ratio = (temp - min_t) / (max_t - min_t)
        y = temp_bottom - ratio * temp_h
        points.append((int(x), int(y)))

    draw_polyline(draw, points, fill=(230, 100, 35), width=3)

    for x, y in points:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(230, 100, 35))


def save_rgb565_raw(img, path):
    width, height = img.size

    with open(path, "wb") as f:
        for y in range(height):
            for x in range(width):
                r, g, b = img.getpixel((x, y))

                v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

                # U Ciebie LCD działał poprawnie z tą kolejnością bajtów.
                f.write(bytes([v >> 8, v & 0xFF]))


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

    # Maxy czerwone.
    draw_temp_row(
        d,
        data["temps_max"],
        11,
        229,
        63,
        (220, 70, 45),
    )

    d.line((13, 84, 227, 84), fill=(225, 232, 240), width=1)

    # Wspólny wykres: godziny + średnia temperatura + opad.
    draw_combined_chart(
        d,
        data["temps"],
        data["temps_min"],
        data["temps_max"],
        data["rain"],
        hours,
        12,
        88,
        228,
        210,
    )

    # Miny niebieskie.
    draw_temp_row(
        d,
        data["temps_min"],
        11,
        229,
        214,
        (40, 130, 210),
    )

    png_path = OUT / data["filename"]
    jpg_path = OUT / data["filename"].replace(".png", ".jpg")
    raw_path = OUT / data["filename"].replace(".png", ".rgb565")

    img.save(png_path, "PNG")
    img.convert("RGB").save(jpg_path, "JPEG", quality=92)
    save_rgb565_raw(img, raw_path)


def write_index(screens, source_info):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    cards = []

    for screen in screens:
        title = screen["title"]
        filename = screen["filename"]
        weather = screen["weather"]
        source_date = screen.get("source_date", "")
        codes = screen.get("codes", [])

        cards.append(
            f"""
    <div class="card">
      <h3>{title}</h3>
      <img src="{filename}">
      <p><code>{filename}</code></p>
      <p class="muted">ikona: <code>{weather}</code></p>
      <p class="muted">data prognozy: <code>{source_date}</code></p>
      <p class="muted">kody: <code>{codes}</code></p>
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

    source_info = f"Źródło: Open-Meteo, Nowy Sącz, lat={LATITUDE}, lon={LONGITUDE}, timezone={TIMEZONE}"
    write_index(screens, source_info)

    print("Generated real weather screens in public/")


if __name__ == "__main__":
    main()
