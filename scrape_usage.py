#!/usr/bin/env python3
"""
Scrape Pokémon Champions usage data and save as JSON.
"""
import re
import html as html_module
import json
import time
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from bs4 import BeautifulSoup

BASE_URL = "https://champs.pokedb.tokyo"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
SCRAPED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def fetch(url, retries=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PokemonUsageBot/1.0)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def parse_list_page(html):
    """Parse ranking list page, return (season_name, [{rank, id, name}])"""
    soup = BeautifulSoup(html, "html.parser")
    # Season name from title
    title = soup.find("title")
    season = ""
    if title:
        m = re.search(r"シーズン[^\s｜|（(]+(?:[（(][^)）]+[)）])?", title.get_text())
        if m:
            season = m.group(0)
    # Pokemon list: each .column inside .columns-pokemon
    pokemon = []
    for col in soup.select(".columns-pokemon .column"):
        link_el = col.select_one("a.list-pokemon")
        rank_el = col.select_one(".pokemon-rank")
        name_el = col.select_one(".pokemon-name")
        if not (link_el and rank_el and name_el):
            continue
        href = link_el.get("href", "")
        m = re.search(r"/pokemon/show/([^?]+)", href)
        pokemon_id = m.group(1) if m else ""
        if not pokemon_id:
            continue
        try:
            rank = int(rank_el.get_text(strip=True))
        except ValueError:
            continue
        name = name_el.get_text(strip=True)
        pokemon.append({"rank": rank, "id": pokemon_id, "name": name})
    return season, pokemon


def parse_detail_page(html):
    """Parse detail page, return dict with moves/abilities/natures/items/ev_spreads/teammates"""
    soup = BeautifulSoup(html, "html.parser")

    # --- Moves ---
    moves = []
    for el in soup.select(".pokemon-trend__move-name[data-move-detail]"):
        raw = el.get("data-move-detail", "")
        try:
            d = json.loads(html_module.unescape(raw))
            moves.append({"rank": d.get("rank"), "name": d.get("name"), "rate": d.get("rate")})
        except Exception:
            pass
    moves = sorted(moves, key=lambda x: x.get("rank", 99))[:10]

    # --- Abilities / Natures / Items from x-data usagePieChart ---
    abilities = []
    natures = []
    items = []
    xdata_pattern = re.compile(r'x-data="([^"]+)"', re.DOTALL)
    for m in xdata_pattern.finditer(html):
        decoded = html_module.unescape(m.group(1))
        if "usagePieChart" not in decoded:
            continue
        arr_match = re.search(r"\[(.+)\]", decoded, re.DOTALL)
        if not arr_match:
            continue
        try:
            arr = json.loads("[" + arr_match.group(1) + "]")
        except Exception:
            continue
        if not arr:
            continue
        first = arr[0]
        if "ability_key" in first:
            abilities = [{"rank": x["rank"], "name": x["name"], "rate": x["rate"]} for x in arr]
        elif "personality_key" in first:
            natures = [{"rank": x["rank"], "name": x["name"], "rate": x["rate"]} for x in arr[:10]]
        elif "item_key" in first:
            items = [{"rank": x["rank"], "name": x["name"], "rate": x["rate"]} for x in arr[:10]]

    # --- EV Spreads ---
    ev_spreads = []
    stats_ul = soup.select_one("ul.usage-list--stats")
    if stats_ul:
        for li in stats_ul.select(".usage-list-item--stats"):
            rank_el = li.select_one(".usage-rank")
            name_el = li.select_one(".usage-name--stats")
            rate_el = li.select_one(".usage-rate")
            chips = li.select(".pokemon-stat-spread__chip")
            ev_detail = {}
            for chip in chips:
                label_el = chip.select_one(".pokemon-stat-spread__label")
                val_el = chip.select_one(".pokemon-stat-spread__value")
                if label_el and val_el:
                    label = label_el.get_text(strip=True)
                    val_text = val_el.get_text(strip=True)
                    try:
                        ev_detail[label] = int(val_text)
                    except Exception:
                        ev_detail[label] = val_text
            if rank_el and name_el and rate_el:
                rate_text = rate_el.get_text(strip=True).rstrip("%")
                try:
                    rate = float(rate_text)
                except Exception:
                    rate = None
                ev_spreads.append({
                    "rank": int(rank_el.get_text(strip=True)),
                    "name": name_el.get_text(strip=True),
                    "rate": rate,
                    "ev": ev_detail,
                })
    ev_spreads = ev_spreads[:7]

    # --- Teammates ---
    teammates = []
    parent = soup.select_one("section.pokemon-trend")
    if parent:
        for ul in parent.select("ul.usage-list"):
            if "usage-list--stats" in (ul.get("class") or []):
                continue
            # Confirm this is a Pokémon list by checking for /pokemon/show/ links
            if not ul.select_one("a[href*='/pokemon/show/']"):
                continue
            for li in ul.select(".usage-list-item"):
                rank_el = li.select_one(".usage-rank")
                name_el = li.select_one(".usage-name")
                link_el = li.select_one("a.usage-pokemon-link")
                if rank_el and name_el:
                    href = link_el.get("href", "") if link_el else ""
                    id_match = re.search(r"/pokemon/show/([^?]+)", href)
                    teammates.append({
                        "rank": int(rank_el.get_text(strip=True)),
                        "id": id_match.group(1) if id_match else "",
                        "name": name_el.get_text(strip=True),
                    })
            break
    teammates = teammates[:10]

    return {
        "moves": moves,
        "abilities": abilities,
        "natures": natures,
        "items": items,
        "ev_spreads": ev_spreads,
        "teammates": teammates,
    }


def scrape_rule(rule, rule_label):
    print(f"\n=== Scraping rule={rule} ({rule_label}) ===")

    # Fetch list page
    list_url = f"{BASE_URL}/pokemon/list?rule={rule}"
    print(f"Fetching list: {list_url}")
    list_html = fetch(list_url)
    season, all_pokemon = parse_list_page(list_html)
    print(f"Season: {season}, Total Pokemon: {len(all_pokemon)}")

    top50 = all_pokemon[:50]
    result_pokemon = []

    for i, poke in enumerate(top50):
        pid = poke["id"]
        detail_url = f"{BASE_URL}/pokemon/show/{pid}?rule={rule}"
        print(f"[{i+1}/50] Fetching {poke['name']} ({pid}) ...")
        try:
            detail_html = fetch(detail_url)
            detail = parse_detail_page(detail_html)
            result_pokemon.append({
                "rank": poke["rank"],
                "id": pid,
                "name": poke["name"],
                **detail
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            result_pokemon.append({
                "rank": poke["rank"],
                "id": pid,
                "name": poke["name"],
                "moves": [], "abilities": [], "natures": [],
                "items": [], "ev_spreads": [], "teammates": [],
            })
        # Be polite
        if i < 49:
            time.sleep(0.5)

    return {
        "season": season,
        "rule": rule_label,
        "scraped_at": SCRAPED_AT,
        "pokemon": result_pokemon,
    }


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved: {path}")


def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(repo_root, "UsedRanking")

    # Single battle (rule=0)
    single_data = scrape_rule(0, "single")
    save_json(single_data, os.path.join(base_dir, "current_single.json"))
    save_json(single_data, os.path.join(base_dir, "history", "single", f"{TODAY}.json"))

    # Double battle (rule=1)
    double_data = scrape_rule(1, "double")
    save_json(double_data, os.path.join(base_dir, "current_double.json"))
    save_json(double_data, os.path.join(base_dir, "history", "double", f"{TODAY}.json"))

    print("\nDone!")


if __name__ == "__main__":
    main()
