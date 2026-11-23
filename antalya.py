"""Refresh the first page of Antalya's public municipal calendar."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

SOURCE = "https://www.antalya.bel.tr/tr/etkinlikler"


def collect():
    events = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(locale="tr-TR")

        def capture(response):
            if response.request.resource_type not in {"xhr", "fetch"} or not response.ok:
                return
            try:
                payload = response.json()
            except Exception:
                return
            pending = [payload]
            while pending:
                item = pending.pop()
                if isinstance(item, list):
                    pending.extend(item)
                elif isinstance(item, dict):
                    pending.extend(item.values())
                    details = item.get("custominclude")
                    if not isinstance(details, dict):
                        continue
                    title = item.get("baslik")
                    start = details.get("StartDate")
                    if isinstance(title, str) and title.strip() and start:
                        venue = item.get("mekan") or details.get("Location")
                        events[(title, str(start))] = dict(
                            title=title.strip(), start=str(start), city="Antalya",
                            venue=venue if isinstance(venue, str) else None,
                            source=SOURCE,
                        )

        page.on("response", capture)
        page.goto(SOURCE, wait_until="domcontentloaded", timeout=90000)
        for _ in range(30):
            page.wait_for_timeout(1000)
            if events:
                break
        if not events:
            months = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
            text = page.locator("body").inner_text()
            pattern = r"(?m)^\s*(?:Pazartesi|Salı|Çarşamba|Perşembe|Cuma|Cumartesi|Pazar),\s*(\d{1,2}) (\w+) (\d{4})\s*\n\s*([^\n]+)"
            for day, month, year, title in re.findall(pattern, text):
                if month in months and title.strip():
                    start = f"{year}-{months.index(month) + 1:02d}-{int(day):02d}"
                    events[(title, start)] = dict(title=title.strip(), start=start, city="Antalya", venue=None, source=SOURCE)
        browser.close()
    if not events:
        raise RuntimeError("Takvimden doğrulanabilir etkinlik alınamadı. Önceki dosya korundu.")
    return [events[key] for key in sorted(events)]


if __name__ == "__main__":
    rows = collect()
    payload = dict(updated_at=datetime.now(timezone.utc).isoformat(), events=rows)
    Path("etkinlikler.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} etkinlik kaydedildi.")
