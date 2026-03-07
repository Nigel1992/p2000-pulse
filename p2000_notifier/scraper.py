"""Simple scraper for alarmfase1.nl region pages to extract the latest call."""
import hashlib
from datetime import datetime

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.alarmfase1.nl/"


def fetch_latest(region_path: str, timeout: int = 15) -> dict | None:
    """Fetch and parse the latest call for a region path.

    Returns a dict with keys like: id, priority_code, message, time, date,
    city, address, postalcode, latitude, longitude, service_type, link
    or None if no calls found.
    """
    url = f"{BASE_URL}{region_path.strip('/')}/"
    headers = {"User-Agent": "p2000-notifier/1.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    if r.status_code == 404:
        return None
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    latest = soup.select_one("#calls .call") or soup.find("div", class_="call")
    if not latest:
        return None

    data: dict = {}
    title_tag = latest.find("b", itemprop="name")
    data["priority_code"] = title_tag.text.strip() if title_tag else ""

    pre_tag = latest.find("pre")
    data["message"] = pre_tag.text.strip() if pre_tag else ""

    time_span = latest.find("span", itemprop="startDate")
    iso_str = time_span.get("content") if time_span else None
    data["absolute_time_str"] = iso_str
    if iso_str:
        try:
            parsed = datetime.fromisoformat(iso_str)
            data["time"] = parsed.strftime("%H:%M")
            data["date"] = parsed.strftime("%Y-%m-%d")
        except Exception:
            data["time"] = time_span.text.strip() if time_span else ""
            data["date"] = ""
    else:
        data["time"] = ""
        data["date"] = ""

    city_tag = latest.find(itemprop="addressLocality")
    data["city"] = city_tag.text.strip() if city_tag else ""

    postal_tag = latest.find(itemprop="postalCode")
    data["postalcode"] = postal_tag.text.strip() if postal_tag else ""

    street_tag = latest.find(itemprop="streetAddress")
    data["address"] = street_tag.text.strip() if street_tag else ""

    # coordinates sometimes present as attributes on the call div
    try:
        lat = latest.get("latitude")
        lon = latest.get("longitude")
        data["latitude"] = float(lat) if lat else None
        data["longitude"] = float(lon) if lon else None
    except Exception:
        data["latitude"] = None
        data["longitude"] = None

    data["service_type"] = latest.get("service") or ""

    link_tag = latest.find("a", href=True)
    if link_tag:
        href = link_tag["href"]
        if href.startswith("http"):
            data["link"] = href
        else:
            data["link"] = BASE_URL.rstrip("/") + "/" + href.lstrip("/")
    else:
        data["link"] = url

    id_src = f"{data.get('absolute_time_str','')}-{data.get('message','')}"
    data["id"] = hashlib.sha256(id_src.encode("utf-8")).hexdigest()[:12]

    return data


def fetch_region_cities(region_path: str, timeout: int = 15) -> list[tuple[str, str]]:
    """Fetch a region page and return a list of (display, city_path) tuples.

    Each tuple contains the human-friendly display name and the canonical
    city path segment used by alarmfase1 (e.g. ('Weesp', 'weesp')). If a
    display name was scraped but no canonical path could be determined the
    path value will be an empty string.
    """
    url = f"{BASE_URL}{region_path.strip('/')}/"
    headers = {"User-Agent": "p2000-notifier/1.0"}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    cities: dict[str, str] = {}

    region_norm = region_path.strip('/').lower()

    def href_to_path(href: str) -> str:
        p = href
        if p.startswith('http'):
            import re as _re

            p = _re.sub(r'^https?://[^/]+/', '', p)
        return p.strip('/').lower()

    # collect from select/option if present (no canonical path available)
    for sel in soup.find_all("select"):
        for opt in sel.find_all("option"):
            txt = opt.get_text(strip=True)
            if txt and len(txt) < 80 and not txt.lower().startswith("alles"):
                cities.setdefault(txt, "")

    # collect anchors linking to city subpaths under the region
    for a in soup.find_all("a", href=True):
        href = a["href"]
        txt = a.get_text(strip=True)
        if not txt or len(txt) > 80:
            continue

        # skip anchors that are part of call entries
        skip = False
        for p in a.parents:
            if p and getattr(p, 'get', None):
                classes = ' '.join(p.get('class') or [])
                if 'call' in classes or 'calls' in classes or (p.get('id') or '').lower().startswith('calls'):
                    skip = True
                    break
        if skip:
            continue

        lowtxt = (txt or '').lower()

        path = href_to_path(href)
        try:
            if region_norm and path.startswith(region_norm + '/'):
                rest = path[len(region_norm) + 1 :]
                parts = [p for p in rest.split('/') if p]
                if parts:
                    city_token = parts[1] if parts[0] == 'plaats' and len(parts) > 1 else parts[0]
                    display = txt or city_token.replace('-', ' ').title()
                    bad_keywords = ['ambulance', 'politie', 'brandweer', 'spoed', 'met', 'naar', 'voor', 'ongeval', 'gepland']
                    if any(k in lowtxt for k in bad_keywords):
                        pass
                    else:
                        cities.setdefault(display, city_token)
                        continue
        except Exception:
            pass

        if 'plaats' in href.lower() or 'plaats' in txt.lower() or '/plaats/' in href.lower():
            try:
                parts = [p for p in href_to_path(href).split('/') if p]
                city_token = next((p for p in reversed(parts) if p not in ('plaats', region_norm, 'provincie', 'postcode')), '')
                if city_token:
                    display = txt or city_token.replace('-', ' ').title()
                    cities.setdefault(display, city_token)
                    continue
            except Exception:
                pass

    for section in soup.select("aside, nav, .places, .plaats, .region, .regions"):
        for a in section.select("a"):
            txt = a.get_text(strip=True)
            if txt and len(txt) < 80 and not txt.lower().startswith("meer"):
                cities.setdefault(txt, "")

    result = [(disp, cities[disp]) for disp in sorted(cities.keys(), key=lambda s: s.lower())]
    return result
