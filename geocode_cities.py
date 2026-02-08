import csv
import json
import time
import os
import sys
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

CACHE_FILE = '/Users/hekman/Desktop/Code/twincities/geocode_cache.json'
INPUT_FILE = '/Users/hekman/Desktop/Code/twincities/twin_cities_raw.csv'
OUTPUT_FILE = '/Users/hekman/Desktop/Code/twincities/app/public/twin_cities.csv'

HEADERS = {'User-Agent': 'TwinCitiesProject/1.0 (educational project)'}

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)

def batch_geocode_wikipedia(titles_batch, cache):
    """Use Wikipedia API to get coordinates for up to 50 titles at once."""
    # Filter out already cached
    to_query = [t for t in titles_batch if t not in cache]
    if not to_query:
        return

    # Wikipedia API supports up to 50 titles per request
    titles_str = '|'.join(to_query[:50])
    url = 'https://en.wikipedia.org/w/api.php'
    params = {
        'action': 'query',
        'titles': titles_str,
        'prop': 'coordinates',
        'format': 'json',
        'colimit': 50,
    }

    try:
        time.sleep(0.2)  # Be polite but much faster than Nominatim
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()

        if 'query' not in data or 'pages' not in data['query']:
            return

        # Map normalized titles back
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

            # Also store by normalized title
            if title != original:
                if 'coordinates' in page and page['coordinates']:
                    cache[title] = cache[original]

    except Exception as e:
        print(f"  Wikipedia API error: {e}")

def geocode_nominatim(geolocator, city, country, cache):
    """Fallback to Nominatim for cities not found via Wikipedia."""
    queries = []
    if country:
        queries.append(f"{city}, {country}")
    queries.append(city)

    for query in queries:
        if query in cache:
            result = cache[query]
            if result:
                return result['lat'], result['lng']
            continue

        try:
            time.sleep(1.05)
            location = geolocator.geocode(query, timeout=10)
            if location:
                cache[query] = {'lat': location.latitude, 'lng': location.longitude}
                return location.latitude, location.longitude
            else:
                cache[query] = None
        except (GeocoderTimedOut, GeocoderServiceError):
            time.sleep(2)
            try:
                location = geolocator.geocode(query, timeout=15)
                if location:
                    cache[query] = {'lat': location.latitude, 'lng': location.longitude}
                    return location.latitude, location.longitude
                cache[query] = None
            except:
                cache[query] = None

    return None, None

def main():
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        pairs = list(csv.DictReader(f))

    print(f"Loaded {len(pairs)} pairs")

    # Collect unique cities
    cities = set()
    for p in pairs:
        cities.add((p['city1'], p['country1']))
        cities.add((p['city2'], p['country2']))

    print(f"Unique cities: {len(cities)}")

    cache = load_cache()

    # Phase 1: Try Wikipedia API (fast, batch of 50)
    print("\n=== Phase 1: Wikipedia API geocoding ===")

    # Collect city names as Wikipedia article titles
    all_city_names = sorted(set(c for c, _ in cities))

    # Filter out already cached
    uncached = [c for c in all_city_names if c not in cache]
    print(f"Cities to query via Wikipedia: {len(uncached)}")

    # Batch process
    batch_size = 50
    for i in range(0, len(uncached), batch_size):
        batch = uncached[i:i+batch_size]
        batch_geocode_wikipedia(batch, cache)
        if i % 500 == 0:
            found = sum(1 for c in uncached[:i+batch_size] if c in cache and cache[c])
            print(f"  [{i}/{len(uncached)}] Found so far: {found}")
            save_cache(cache)
            sys.stdout.flush()

    save_cache(cache)

    # Count results
    found_wiki = sum(1 for c in all_city_names if c in cache and cache[c])
    print(f"Wikipedia found: {found_wiki}/{len(all_city_names)}")

    # Phase 2: For cities not found, try with "city, country" format via Wikipedia search
    print("\n=== Phase 2: Wikipedia search with country ===")
    not_found = []
    for city, country in sorted(cities):
        query = f"{city}, {country}" if country else city
        if city in cache and cache[city]:
            continue
        if query in cache and cache[query]:
            continue
        not_found.append((city, country))

    print(f"Still need geocoding: {len(not_found)}")

    # Try Wikipedia search API for unfound cities
    for i in range(0, len(not_found), batch_size):
        batch_cities = [c for c, _ in not_found[i:i+batch_size]]
        batch_geocode_wikipedia(batch_cities, cache)
        if i % 500 == 0 and i > 0:
            print(f"  [{i}/{len(not_found)}]")
            save_cache(cache)
            sys.stdout.flush()

    save_cache(cache)

    # Phase 3: Nominatim fallback for remaining (with limit)
    print("\n=== Phase 3: Nominatim fallback ===")
    still_missing = []
    for city, country in sorted(cities):
        if city in cache and cache[city]:
            continue
        query = f"{city}, {country}" if country else city
        if query in cache:
            continue
        still_missing.append((city, country))

    print(f"Need Nominatim fallback: {len(still_missing)}")

    if still_missing:
        geolocator = Nominatim(user_agent="twin_cities_project_v3")
        # Limit to reasonable amount - prioritize by frequency
        from collections import Counter
        city_freq = Counter()
        for p in pairs:
            city_freq[(p['city1'], p['country1'])] += 1
            city_freq[(p['city2'], p['country2'])] += 1

        # Sort by frequency, geocode most important first
        still_missing.sort(key=lambda x: -city_freq.get(x, 0))

        # Limit to top 3000 to keep it reasonable (~50 minutes)
        limit = min(len(still_missing), 3000)
        print(f"Geocoding top {limit} by frequency via Nominatim...")

        for i, (city, country) in enumerate(still_missing[:limit]):
            if i % 100 == 0:
                print(f"  [{i}/{limit}] ({i/limit*100:.1f}%)")
                save_cache(cache)
                sys.stdout.flush()

            geocode_nominatim(geolocator, city, country, cache)

        save_cache(cache)

    # Build geocoded dictionary
    geocoded = {}
    for city, country in cities:
        key = f"{city}|{country}"
        # Try various cache keys
        query = f"{city}, {country}" if country else city
        if city in cache and cache[city]:
            geocoded[key] = (cache[city]['lat'], cache[city]['lng'])
        elif query in cache and cache[query]:
            geocoded[key] = (cache[query]['lat'], cache[query]['lng'])

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

    print(f"\nGeocoded pairs: {len(output_rows)}")
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
