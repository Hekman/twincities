import csv
from collections import Counter

RAW_PATH = "/Users/hekman/Desktop/Code/twincities/twin_cities_raw.csv"
GEO_PATH = "/Users/hekman/Desktop/Code/twincities/app/public/twin_cities.csv"
OUT_PATH = "/Users/hekman/Desktop/Code/twincities/missing_cities.csv"


def read_pairs(path):
    """Return set of (city1, country1, city2, country2) tuples."""
    pairs = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (
                row["city1"].strip(),
                row["country1"].strip(),
                row["city2"].strip(),
                row["country2"].strip(),
            )
            pairs.add(key)
    return pairs


def main():
    raw_pairs = read_pairs(RAW_PATH)
    geo_pairs = read_pairs(GEO_PATH)

    missing_pairs = raw_pairs - geo_pairs

    print(f"Raw pairs:      {len(raw_pairs)}")
    print(f"Geocoded pairs: {len(geo_pairs)}")
    print(f"Missing pairs:  {len(missing_pairs)}")
    print()

    # Collect all cities that appear in geocoded data (both sides)
    geocoded_cities = set()
    with open(GEO_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geocoded_cities.add((row["city1"].strip(), row["country1"].strip()))
            geocoded_cities.add((row["city2"].strip(), row["country2"].strip()))

    # Collect all cities from missing pairs
    cities_in_missing = set()
    for c1, co1, c2, co2 in missing_pairs:
        cities_in_missing.add((c1, co1))
        cities_in_missing.add((c2, co2))

    # Cities that need geocoding: appear in missing pairs but NOT in any geocoded pair
    missing_cities = cities_in_missing - geocoded_cities

    print(f"Unique cities in missing pairs: {len(cities_in_missing)}")
    print(f"Of those, cities with NO geocoded coords anywhere: {len(missing_cities)}")
    print()

    # Count how often each missing city appears across all missing pairs
    city_counter = Counter()
    for c1, co1, c2, co2 in missing_pairs:
        city_counter[(c1, co1)] += 1
        city_counter[(c2, co2)] += 1

    print("Top 20 most common cities in missing pairs:")
    for (city, country), count in city_counter.most_common(20):
        tag = " *" if (city, country) in missing_cities else ""
        print(f"  {count:4d}  {city}, {country}{tag}")
    print("  (* = city has no geocoded coordinates at all)")
    print()

    # Write missing cities to CSV
    missing_sorted = sorted(missing_cities, key=lambda x: (x[1], x[0]))
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["city", "country"])
        for city, country in missing_sorted:
            writer.writerow([city, country])

    print(f"Wrote {len(missing_sorted)} missing cities to {OUT_PATH}")


if __name__ == "__main__":
    main()
