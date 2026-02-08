"""
Targeted geocoder for the ~2,398 cities that the first pass missed.
Cleans up city names (removes parentheticals, splits compound names, fixes country names)
and tries multiple geocoding strategies.
"""
import csv
import json
import re
import time
import os
import sys
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

CACHE_FILE = '/Users/hekman/Desktop/Code/twincities/geocode_cache.json'
MISSING_FILE = '/Users/hekman/Desktop/Code/twincities/missing_cities.csv'
RAW_FILE = '/Users/hekman/Desktop/Code/twincities/twin_cities_raw.csv'
OUTPUT_FILE = '/Users/hekman/Desktop/Code/twincities/app/public/twin_cities.csv'
HEADERS = {'User-Agent': 'TwinCitiesProject/2.0 (educational project)'}


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)


def clean_city_name(city):
    """Generate multiple cleaned variants of a city name for geocoding."""
    variants = []

    # Original
    variants.append(city)

    # Remove parenthetical qualifiers: "Esch (Haaren)" -> "Esch"
    no_parens = re.sub(r'\s*\([^)]*\)', '', city).strip()
    if no_parens and no_parens != city:
        variants.append(no_parens)

    # Handle compound names: "Haaren -- Esch" -> try both "Haaren" and "Esch"
    if ' -- ' in city:
        parts = city.split(' -- ')
        for part in parts:
            clean = re.sub(r'\s*\([^)]*\)', '', part).strip()
            if clean:
                variants.append(clean)

    # Handle "City-District" patterns: "Joniškis -- Zagare" -> "Zagare"
    if ' - ' in city:
        parts = city.split(' - ')
        for part in parts:
            clean = re.sub(r'\s*\([^)]*\)', '', part).strip()
            if clean:
                variants.append(clean)

    # Remove common suffixes that confuse geocoders
    for suffix in [' (rural gmina)', ' (urban gmina)', ' (city)', ' (commune)',
                   ' (municipality)', ' (district)', ' (province)', ' (county)',
                   ' (town)', ' (village)', ' Oblast', ' Raion']:
        if city.lower().endswith(suffix.lower()):
            variants.append(city[:len(city)-len(suffix)].strip())

    # Remove leading/trailing punctuation
    variants = [v.strip(' ,.-') for v in variants if v.strip(' ,.-')]

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)

    return unique


def clean_country(country):
    """Fix country names that confuse geocoders."""
    fixes = {
        'Georgia (country)': 'Georgia',
        'Republic of Ireland': 'Ireland',
        'Republic of Korea': 'South Korea',
        'Democratic Republic of the Congo': 'DR Congo',
        'Republic of the Congo': 'Republic of Congo',
        'People\'s Republic of China': 'China',
        'Republic of China': 'Taiwan',
        'Palestinian territories': 'Palestine',
        'Transnistria': 'Moldova',
        'Northern Cyprus': 'Cyprus',
        'Kosovo': 'Kosovo',
    }
    # Also handle "Algarve, Portugal" -> "Portugal"
    if ',' in country:
        parts = country.split(',')
        return parts[-1].strip()
    return fixes.get(country, country)


def batch_geocode_wikipedia(titles, cache):
    """Use Wikipedia API to get coordinates for up to 50 titles at once."""
    to_query = [t for t in titles if t not in cache]
    if not to_query:
        return

    url = 'https://en.wikipedia.org/w/api.php'
    params = {
        'action': 'query',
        'titles': '|'.join(to_query[:50]),
        'prop': 'coordinates',
        'format': 'json',
        'colimit': 50,
    }

    try:
        time.sleep(0.3)
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()

        if 'query' not in data or 'pages' not in data['query']:
            return

        normalized = {}
        if 'normalized' in data['query']:
            for n in data['query']['normalized']:
                normalized[n['to']] = n['from']

        for page_id, page in data['query']['pages'].items():
            title = page.get('title', '')
            original = normalized.get(title, title)

            if 'coordinates' in page and page['coordinates']:
                coords = page['coordinates'][0]
                cache[original] = {'lat': coords['lat'], 'lng': coords['lon']}
            else:
                cache[original] = None

            if title != original:
                if 'coordinates' in page and page['coordinates']:
                    cache[title] = cache[original]

    except Exception as e:
        print(f"  Wikipedia API error: {e}")


def wikipedia_search_geocode(query, cache):
    """Use Wikipedia search API to find a page, then get its coordinates."""
    if query in cache:
        return cache[query]

    url = 'https://en.wikipedia.org/w/api.php'
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'srlimit': 3,
        'format': 'json',
    }

    try:
        time.sleep(0.3)
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()

        if 'query' not in data or 'search' not in data['query']:
            cache[query] = None
            return None

        titles = [r['title'] for r in data['query']['search']]
        if not titles:
            cache[query] = None
            return None

        # Get coordinates for search results
        params2 = {
            'action': 'query',
            'titles': '|'.join(titles),
            'prop': 'coordinates',
            'format': 'json',
            'colimit': 10,
        }
        time.sleep(0.3)
        resp2 = requests.get(url, params=params2, headers=HEADERS, timeout=15)
        data2 = resp2.json()

        if 'query' in data2 and 'pages' in data2['query']:
            for page_id, page in data2['query']['pages'].items():
                if 'coordinates' in page and page['coordinates']:
                    coords = page['coordinates'][0]
                    result = {'lat': coords['lat'], 'lng': coords['lon']}
                    cache[query] = result
                    return result

        cache[query] = None
        return None

    except Exception as e:
        cache[query] = None
        return None


def geocode_nominatim(geolocator, query, cache):
    """Nominatim geocoding with caching."""
    if query in cache:
        return cache[query]

    try:
        time.sleep(1.05)
        location = geolocator.geocode(query, timeout=10)
        if location:
            result = {'lat': location.latitude, 'lng': location.longitude}
            cache[query] = result
            return result
        cache[query] = None
    except (GeocoderTimedOut, GeocoderServiceError):
        time.sleep(2)
        try:
            location = geolocator.geocode(query, timeout=15)
            if location:
                result = {'lat': location.latitude, 'lng': location.longitude}
                cache[query] = result
                return result
            cache[query] = None
        except:
            cache[query] = None
    return None


def lookup_city(city, country, cache, geolocator):
    """Try multiple strategies to geocode a city."""
    clean_ctry = clean_country(country)
    variants = clean_city_name(city)

    # Strategy 1: Wikipedia API with cleaned names
    for v in variants:
        if v in cache and cache[v]:
            return cache[v]

    # Strategy 2: Wikipedia API with "city, country"
    for v in variants:
        query = f"{v}, {clean_ctry}" if clean_ctry else v
        if query in cache and cache[query]:
            return cache[query]

    # Strategy 3: Wikipedia search with city + country
    for v in variants[:2]:  # Only try first 2 variants
        query = f"{v} {clean_ctry}"
        result = wikipedia_search_geocode(query, cache)
        if result:
            return result

    # Strategy 4: Nominatim with cleaned names
    for v in variants[:2]:
        query = f"{v}, {clean_ctry}" if clean_ctry else v
        result = geocode_nominatim(geolocator, query, cache)
        if result:
            return result

    # Strategy 5: Nominatim with just the city name (no country)
    for v in variants[:1]:
        result = geocode_nominatim(geolocator, v, cache)
        if result:
            return result

    return None


def main():
    cache = load_cache()

    # Load missing cities
    with open(MISSING_FILE, 'r', encoding='utf-8') as f:
        missing = list(csv.DictReader(f))

    print(f"Missing cities to geocode: {len(missing)}")

    # Phase 1: Wikipedia batch with cleaned names (fast)
    print("\n=== Phase 1: Wikipedia API with cleaned names ===")
    all_variants = []
    for row in missing:
        city = row['city']
        variants = clean_city_name(city)
        all_variants.extend(variants)

    # Deduplicate
    all_variants = list(set(all_variants))
    uncached = [v for v in all_variants if v not in cache]
    print(f"Unique name variants to try: {len(all_variants)} ({len(uncached)} uncached)")

    for i in range(0, len(uncached), 50):
        batch = uncached[i:i+50]
        batch_geocode_wikipedia(batch, cache)
        if i % 500 == 0:
            print(f"  [{i}/{len(uncached)}]")
            save_cache(cache)
            sys.stdout.flush()

    save_cache(cache)

    # Check how many are now found
    found = 0
    still_missing = []
    for row in missing:
        city = row['city']
        country = row['country']
        variants = clean_city_name(city)
        result = None
        for v in variants:
            if v in cache and cache[v]:
                result = cache[v]
                break
            q = f"{v}, {clean_country(country)}"
            if q in cache and cache[q]:
                result = cache[q]
                break
        if result:
            found += 1
        else:
            still_missing.append(row)

    print(f"Found after Phase 1: {found}/{len(missing)}")
    print(f"Still missing: {len(still_missing)}")

    # Phase 2: Wikipedia search + Nominatim for remaining
    print(f"\n=== Phase 2: Wikipedia search + Nominatim ({len(still_missing)} cities) ===")
    geolocator = Nominatim(user_agent="twin_cities_project_v4")

    newly_found = 0
    for i, row in enumerate(still_missing):
        city = row['city']
        country = row['country']

        if i % 50 == 0:
            print(f"  [{i}/{len(still_missing)}] newly found: {newly_found}")
            save_cache(cache)
            sys.stdout.flush()

        result = lookup_city(city, country, cache, geolocator)
        if result:
            newly_found += 1

    save_cache(cache)
    print(f"Found in Phase 2: {newly_found}")
    print(f"Total newly found: {found + newly_found}/{len(missing)}")

    # Now rebuild the full output CSV
    print("\n=== Rebuilding output CSV ===")
    with open(RAW_FILE, 'r', encoding='utf-8') as f:
        pairs = list(csv.DictReader(f))

    # Collect all cities
    all_cities = set()
    for p in pairs:
        all_cities.add((p['city1'], p['country1']))
        all_cities.add((p['city2'], p['country2']))

    # Build geocoded dictionary
    geocoded = {}
    for city, country in all_cities:
        key = f"{city}|{country}"
        clean_ctry = clean_country(country)
        variants = clean_city_name(city)

        for v in variants:
            if v in cache and cache[v]:
                geocoded[key] = (cache[v]['lat'], cache[v]['lng'])
                break
            q = f"{v}, {clean_ctry}" if clean_ctry else v
            if q in cache and cache[q]:
                geocoded[key] = (cache[q]['lat'], cache[q]['lng'])
                break
            q2 = f"{v} {clean_ctry}"
            if q2 in cache and cache[q2]:
                geocoded[key] = (cache[q2]['lat'], cache[q2]['lng'])
                break

    print(f"Total geocoded cities: {len(geocoded)}/{len(all_cities)}")

    # Build output
    output_rows = []
    skipped = 0
    for p in pairs:
        key1 = f"{p['city1']}|{p['country1']}"
        key2 = f"{p['city2']}|{p['country2']}"

        if key1 in geocoded and key2 in geocoded:
            lat1, lng1 = geocoded[key1]
            lat2, lng2 = geocoded[key2]
            output_rows.append({
                'city1': p['city1'],
                'country1': p['country1'],
                'lat1': round(lat1, 4),
                'lng1': round(lng1, 4),
                'city2': p['city2'],
                'country2': p['country2'],
                'lat2': round(lat2, 4),
                'lng2': round(lng2, 4),
            })
        else:
            skipped += 1

    print(f"\nGeocoded pairs: {len(output_rows)}/{len(pairs)}")
    print(f"Skipped (missing coords): {skipped}")
    print(f"Coverage: {len(output_rows)/len(pairs)*100:.1f}%")

    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'city1', 'country1', 'lat1', 'lng1',
            'city2', 'country2', 'lat2', 'lng2'
        ])
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Saved to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
