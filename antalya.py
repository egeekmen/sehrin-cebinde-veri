"""Refresh the first page of Antalya's public municipal calendar."""
import json
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
        for _ in range(60):
            page.wait_for_timeout(1000)
            if events:
                break
        if not events:
            cards = page.locator("[ng-bind*='baslik'], [data-ng-bind*='baslik'], h6")
            for card in cards.all():
                row = card.evaluate("""el => {
                    if (!window.angular) return null;
                    const scope = angular.element(el).scope();
                    const item = scope && scope.item;
                    if (!item || !item.baslik) return null;
                    const details = item.custominclude || {};
                    return {title:item.baslik, start:details.StartDate, venue:item.mekan || null};
                }""")
                if row and row.get("start"):
                    row.update(city="Antalya", source=SOURCE)
                    events[(row["title"], str(row["start"]))] = row
        if not events:
            print("Calendar page:", page.title(), page.locator("body").inner_text()[-2400:])
        browser.close()
    if not events:
        raise RuntimeError("Takvimden doğrulanabilir etkinlik alınamadı. Önceki dosya korundu.")
    return [events[key] for key in sorted(events)]


if __name__ == "__main__":
    rows = collect()
    payload = dict(updated_at=datetime.now(timezone.utc).isoformat(), events=rows)
    Path("etkinlikler.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(rows)} etkinlik kaydedildi.")
