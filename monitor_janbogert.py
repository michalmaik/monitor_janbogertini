import json
import time
import re
import os
from datetime import datetime, timezone
import requests

# ── Konfiguracja ─────────────────────────────────────────────────────────────

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1482706376999567451/V-RAPCZVTlZVJFibiDmjueJeN8ftw9YZZ0xliGj8oXlSTwb7kzMVfsT_o6h5MG8wyMFV"
SOURCE_URL       = "https://janbogert.nl/occasions/?brand=tesla&model=model-3&fuel=e"

STATE_FILE   = "janbogert_state.json"
HISTORY_FILE = "janbogert_history.json"

# Filtry
MAX_EUR      = 18900
MAX_KM       = 135000
MAX_YEAR     = 2021
MIN_YEAR     = 2018

HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "nl-NL,nl;q=0.9,en;q=0.8",
}


# ── Pobieranie i parsowanie ───────────────────────────────────────────────────

def fetch_cars():
    cars = {}
    try:
        resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=20)
        print(f"  Status: {resp.status_code}")
        if resp.status_code != 200:
            return cars
        html = resp.text
    except Exception as e:
        print(f"  Błąd pobierania: {e}")
        return cars

    # Znajdź wszystkie linki do ogłoszeń Tesli Model 3
    # Format: /occasions/NUMER-tesla-model-3-.../
    blocks = re.findall(
        r'<a\s+href="(https://janbogert\.nl/occasions/\d+-tesla-model-3-[^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL
    )

    # Lepiej parsować bloki kart ogłoszeń
    # Każda karta wygląda jak: <a href="..."><img ...><h2>Tesla Model 3</h2>... rok ... km ... cena</a>
    car_pattern = re.findall(
        r'href="(https://janbogert\.nl/occasions/(\d+)-tesla-model-3-[^"]+)".*?'
        r'<h2[^>]*>(.*?)</h2>.*?'
        r'(\d{4})\s*</.*?'
        r'([\d\.]+)\s*km.*?'
        r'€\s*([\d\.]+),-',
        html, re.DOTALL
    )

    if not car_pattern:
        # Fallback: parsuj sekcje osobno
        # Wyciągnij wszystkie bloki <a href="/occasions/NNN-tesla...">...</a>
        sections = re.split(r'(?=<a\s+href="https://janbogert\.nl/occasions/\d+-tesla)', html)
        for section in sections:
            try:
                url_match = re.search(r'href="(https://janbogert\.nl/occasions/(\d+)-tesla-model-3-[^"]+)"', section)
                if not url_match:
                    continue
                url    = url_match.group(1)
                car_id = url_match.group(2)

                title_match = re.search(r'<h2[^>]*>(.*?)</h2>', section, re.DOTALL)
                if not title_match:
                    continue
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                title = re.sub(r'\s+', ' ', title).strip()

                year_match = re.search(r'\b(201[5-9]|202[0-5])\b', section)
                year = int(year_match.group(1)) if year_match else 0

                km_match = re.search(r'([\d\.]+)\s*km', section)
                mileage = 0
                mileage_str = ""
                if km_match:
                    mileage_str = km_match.group(0).strip()
                    mileage = int(re.sub(r'[^\d]', '', km_match.group(1)))

                price_match = re.search(r'€\s*([\d\.]+),-', section)
                price = 0
                if price_match:
                    price = int(re.sub(r'[^\d]', '', price_match.group(1)))

                # Filtruj
                if price > MAX_EUR:
                    continue
                if mileage and mileage > MAX_KM:
                    continue
                if year and (year < MIN_YEAR or year > MAX_YEAR):
                    continue
                if not price or not year:
                    continue

                cars[car_id] = {
                    "id":          car_id,
                    "url":         url,
                    "title":       title,
                    "year":        year,
                    "price":       price,
                    "mileage":     mileage,
                    "mileage_str": mileage_str,
                }
            except Exception as e:
                print(f"  Błąd parsowania sekcji: {e}")
        return cars

    for url, car_id, title, year, km_raw, price_raw in car_pattern:
        try:
            title   = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', title)).strip()
            year    = int(year)
            mileage = int(re.sub(r'[^\d]', '', km_raw))
            price   = int(re.sub(r'[^\d]', '', price_raw))

            if price > MAX_EUR:
                continue
            if mileage > MAX_KM:
                continue
            if year < MIN_YEAR or year > MAX_YEAR:
                continue

            cars[car_id] = {
                "id":          car_id,
                "url":         url,
                "title":       title,
                "year":        year,
                "price":       price,
                "mileage":     mileage,
                "mileage_str": f"{mileage:,} km".replace(",", "."),
            }
        except Exception as e:
            print(f"  Błąd parsowania: {e}")

    return cars


# ── Stan i historia ───────────────────────────────────────────────────────────

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def update_history(history, car_id, price):
    if car_id not in history:
        history[car_id] = []
    last = history[car_id][-1] if history[car_id] else None
    if not last or last["price"] != price:
        history[car_id].append({
            "price": price,
            "date":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        })
    history[car_id] = history[car_id][-20:]
    return history


def format_price_history(entries):
    if len(entries) < 2:
        return None
    lines = []
    prev  = None
    for entry in entries[-5:]:
        if prev is None:              trend = ""
        elif entry["price"] < prev:   trend = " 📉"
        elif entry["price"] > prev:   trend = " 📈"
        else:                         trend = ""
        lines.append(f"{entry['date']}: €{entry['price']:,}{trend}".replace(",", " "))
        prev = entry["price"]
    return "\n".join(lines)


# ── Discord ───────────────────────────────────────────────────────────────────

def send_discord(embeds):
    resp = requests.post(DISCORD_WEBHOOK, json={"embeds": embeds}, timeout=10)
    print(f"  Discord: {resp.status_code}")
    resp.raise_for_status()


def build_new_car_embed(car):
    url     = car.get("url", "")
    title   = car.get("title", "Tesla Model 3")
    price   = car.get("price", 0)
    year    = car.get("year", "—")
    mileage = car.get("mileage_str", "—") or "—"

    lines = [
        f"🇳🇱 **{title}**",
        f"💰 €{price:,}".replace(",", " "),
        f"📅 {year}  |  🛣️ {mileage}",
        f"🔗 [Zobacz na janbogert.nl]({url})",
    ]
    return {
        "title":       "🚗 Nowe Tesla w Jan Bogert!",
        "description": "\n".join(lines),
        "color":       0x1DB954,
        "footer":      {"text": f"Jan Bogert Monitor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


def build_price_drop_embed(car, old_price, new_price, history):
    url      = car.get("url", "")
    title    = car.get("title", "Tesla Model 3")
    year     = car.get("year", "—")
    mileage  = car.get("mileage_str", "—") or "—"
    diff     = old_price - new_price
    pct      = round((old_price - new_price) / old_price * 100, 1)

    lines = [
        f"🇳🇱 **{title}**",
        f"💰 €{old_price:,} → €{new_price:,} (-€{diff:,}, -{pct}%)".replace(",", " "),
        f"📅 {year}  |  🛣️ {mileage}",
        f"🔗 [Zobacz na janbogert.nl]({url})",
    ]
    history_str = format_price_history(history.get(car.get("id", ""), []))
    if history_str:
        lines.append(f"\n📊 Historia:\n{history_str}")

    return {
        "title":       "📉 Spadek ceny w Jan Bogert!",
        "description": "\n".join(lines),
        "color":       0xF0A500,
        "footer":      {"text": f"Jan Bogert Monitor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


def build_test_embed(current_cars):
    lines = []
    for car in sorted(current_cars.values(), key=lambda x: x.get("price", 0)):
        price   = car.get("price", 0)
        title   = car.get("title", "?")
        url     = car.get("url", "")
        mileage = car.get("mileage_str", "") or ""
        year    = car.get("year", "")
        lines.append(f"🇳🇱 [{title}]({url}) — €{price:,} · {year} · {mileage}".replace(",", " "))

    return {
        "title":       "🔧 Test — Jan Bogert bot działa!",
        "description": "\n".join(lines) if lines else "Brak aut spełniających kryteria.",
        "color":       0x3498db,
        "fields": [
            {"name": "Aut w ofercie", "value": str(len(current_cars)),         "inline": True},
            {"name": "Filtr ceny",    "value": f"max €{MAX_EUR:,}".replace(",", " "), "inline": True},
            {"name": "Filtr km",      "value": f"max {MAX_KM:,} km".replace(",", " "), "inline": True},
            {"name": "Roczniki",      "value": f"{MIN_YEAR}–{MAX_YEAR}",       "inline": True},
        ],
        "footer": {"text": f"Jan Bogert Monitor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


def should_send_daily_summary():
    now = datetime.now(timezone.utc)
    return now.hour == 8 and now.minute < 15


def build_daily_summary_embed(current_cars):
    if not current_cars:
        return {
            "title":       "📊 Dzienne podsumowanie — Jan Bogert",
            "description": "Brak aut spełniających kryteria.",
            "color":       0x3498db,
            "footer":      {"text": f"Jan Bogert Monitor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
        }
    lines = []
    for car in sorted(current_cars.values(), key=lambda x: x.get("price", 0)):
        price   = car.get("price", 0)
        title   = car.get("title", "?")[:50]
        url     = car.get("url", "")
        mileage = car.get("mileage_str", "") or ""
        year    = car.get("year", "")
        lines.append(f"[{title}]({url}) — €{price:,} · {year} · {mileage}".replace(",", " "))

    return {
        "title":       f"📊 Dzienne podsumowanie — {len(current_cars)} aut",
        "description": f"Filtr: {MIN_YEAR}–{MAX_YEAR}, max €{MAX_EUR:,}, max {MAX_KM:,} km".replace(",", " "),
        "color":       0x3498db,
        "fields": [{"name": "Auta", "value": "\n".join(lines[:25]) or "brak", "inline": False}],
        "footer":      {"text": f"Jan Bogert Monitor · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"},
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    is_manual = os.environ.get("MANUAL_RUN", "false").lower() == "true"

    now = datetime.now(timezone.utc)
    print(f"[{now.isoformat()}] Start monitorowania Jan Bogert...")

    is_first_run = not os.path.exists(STATE_FILE)
    if is_first_run:
        print("  ⚠️  Pierwsze uruchomienie — zapisuję stan BEZ wysyłania powiadomień.")

    print("\nPobieram auta...")
    current_cars = fetch_cars()
    print(f"Aut znalezionych: {len(current_cars)}")

    previous_state = load_state()
    history        = load_history()
    print(f"Poprzedni stan: {len(previous_state)} aut")

    for car_id, car in current_cars.items():
        history = update_history(history, car_id, car.get("price", 0))

    embeds_new   = []
    embeds_drops = []

    if not is_first_run:
        for car_id, car in current_cars.items():
            if car_id not in previous_state:
                print(f"  NOWE: {car_id} €{car.get('price')}")
                embeds_new.append(build_new_car_embed(car))

        for car_id, car in current_cars.items():
            price     = car.get("price")
            old_price = previous_state.get(car_id, {}).get("price")
            if price and old_price and price < old_price:
                print(f"  SPADEK: {car_id} €{old_price} -> €{price}")
                embeds_drops.append(build_price_drop_embed(car, old_price, price, history))
            elif price and old_price and price > old_price:
                print(f"  WZROST (pominięty): {car_id} €{old_price} -> €{price}")
    else:
        print(f"  Pierwsze uruchomienie — pominięto {len(current_cars)} aut.")

    save_state({
        car_id: {
            "price":       car.get("price"),
            "title":       car.get("title", ""),
            "url":         car.get("url", ""),
            "seen_at":     now.strftime("%Y-%m-%d %H:%M"),
        }
        for car_id, car in current_cars.items()
    })
    save_history(history)

    if embeds_new:
        for i in range(0, len(embeds_new), 10):
            send_discord(embeds_new[i:i+10])
        print(f"  Wysłano {len(embeds_new)} powiadomień o nowych autach.")

    if embeds_drops:
        for i in range(0, len(embeds_drops), 10):
            send_discord(embeds_drops[i:i+10])
        print(f"  Wysłano {len(embeds_drops)} powiadomień o spadkach cen.")

    if should_send_daily_summary() and not is_first_run:
        send_discord([build_daily_summary_embed(current_cars)])
        print("  Wysłano dzienne podsumowanie.")

    if is_manual:
        send_discord([build_test_embed(current_cars)])
        print("  Wysłano powiadomienie testowe.")
    elif not embeds_new and not embeds_drops:
        print("Brak zmian.")


if __name__ == "__main__":
    main()
