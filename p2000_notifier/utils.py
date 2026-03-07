import math
import re
import requests


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometers between two points."""
    # Earth radius
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def geocode_nominatim(query: str) -> tuple[float, float] | None:
    """Simple single-result geocode via Nominatim OpenStreetMap.

    Returns (lat, lon) or None.
    """
    # If the query looks like a Dutch address (postcode present or common NL city),
    # prefer PDOK (BAG) geocoding which is authoritative for Dutch addresses.
    if re.search(r"\b\d{4}\s?[A-Za-z]{2}\b", query) or re.search(r"\b(amsterdam|rotterdam|utrecht|den haag|den-haag|haarlem|groningen|eindhoven|nijmegen|maastricht|tilburg|alkmaar|weesp)\b", query, re.IGNORECASE):
        try:
            pdok = _geocode_pdok(query)
            if pdok:
                return pdok
        except Exception:
            # if PDOK fails, fall back to Nominatim below
            pass

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 1,
    }
    headers = {"User-Agent": "p2000-notifier/1.0 (contact: none)"}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None

    # Prefer most precise result: house/building with smallest bounding box
    def bbox_area(item: dict) -> float:
        bb = item.get("boundingbox")
        if not bb or len(bb) < 4:
            return float("inf")
        try:
            south = float(bb[0])
            north = float(bb[1])
            west = float(bb[2])
            east = float(bb[3])
            return abs(north - south) * abs(east - west)
        except Exception:
            return float("inf")
    precise_types = {"house", "building", "residential", "apartments", "public_building"}

    # Extract house number and road guess from the query to prefer exact matches
    house_num = None
    m = re.search(r"\b(\d+\w?)\b", query)
    if m:
        house_num = m.group(1)

    # pick segment that contains the house number if present, else last segment
    segments = re.split(r"[,-–—|]", query)
    seg_with_num = None
    if house_num:
        for seg in segments:
            if re.search(r"\b" + re.escape(house_num) + r"\b", seg):
                seg_with_num = seg
                break
    seg = seg_with_num if seg_with_num is not None else segments[-1]
    road_guess = re.sub(r"\b\d+\w?\b", "", seg).strip()

    def normalize(s: str) -> str:
        return re.sub(r"\W+", " ", (s or "")).lower().strip()

    norm_road = normalize(road_guess)

    candidates = []
    for item in data:
        t = item.get("type", "").lower()
        cls = item.get("class", "").lower()
        area = bbox_area(item)
        is_precise = (t in precise_types) or (cls == "building")
        importance = float(item.get("importance", 0) or 0)

        score = 0
        addr = item.get("address") or {}
        cand_house = addr.get("house_number")
        if house_num and cand_house:
            try:
                if str(cand_house).lower() == str(house_num).lower():
                    score += 200
            except Exception:
                pass

        # road matching
        cand_road = addr.get("road") or addr.get("residential") or addr.get("pedestrian") or addr.get("path") or item.get("display_name")
        norm_cand_road = normalize(cand_road)
        if norm_road and norm_cand_road:
            if norm_road == norm_cand_road:
                score += 150
            elif norm_road in norm_cand_road or norm_cand_road in norm_road:
                score += 80

        # prefer precise types
        if is_precise:
            score += 50

        # final candidate tuple: higher score first, then prefer precise, smaller bbox, higher importance
        candidates.append(( -score, not is_precise, area, -importance, item))

    # sort and pick best
    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    best = candidates[0][4]
    try:
        return float(best["lat"]), float(best["lon"])
    except Exception:
        try:
            first = data[0]
            return float(first["lat"]), float(first["lon"])
        except Exception:
            return None


def _geocode_pdok(query: str) -> tuple[float, float] | None:
    """Geocode using PDOK locatieserver (BAG-backed). Returns (lat, lon) or None.

    PDOK `centroide_ll` is returned as "lon,lat" so parse accordingly.
    """
    try:
        base = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
        params = {"q": query, "fq": "type:adres", "rows": 5}
        headers = {"User-Agent": "p2000-notifier/1.0 (contact: none)", "Accept": "application/json"}
        r = requests.get(base, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        j = r.json()
        docs = j.get("response", {}).get("docs", [])
        if not docs:
            return None

        # Parse house number from query if present
        house_num = None
        m = re.search(r"\b(\d+\w?)\b", query)
        if m:
            house_num = m.group(1)

        # Prefer docs matching the house number, else take best doc
        best_doc = None
        if house_num:
            for d in docs:
                if str(d.get("huisnummer") or d.get("huisnr") or "").lower() == house_num.lower():
                    best_doc = d
                    break

        if not best_doc:
            best_doc = docs[0]

        centroide = best_doc.get("centroide_ll") or best_doc.get("centroide")
        if not centroide:
            return None
        # centroide_ll is 'lon,lat'
        parts = str(centroide).split(",")
        if len(parts) >= 2:
            lon = float(parts[0])
            lat = float(parts[1])
            return lat, lon
    except Exception:
        return None
    return None
