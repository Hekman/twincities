import requests
from bs4 import BeautifulSoup
import csv
import re
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TwinCitiesProject/1.0'
}

def get_page(url):
    """Fetch a Wikipedia page and return BeautifulSoup object."""
    time.sleep(0.3)
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise

def get_country_from_title(soup):
    """Extract country name from page title."""
    title_tag = soup.find('h1', {'id': 'firstHeading'})
    if not title_tag:
        return ""
    title = title_tag.get_text(strip=True)
    m = re.search(r'sister cities in (?:the )?(.+)', title, re.IGNORECASE)
    return m.group(1).strip() if m else ""

def extract_country_subpage_urls(soup):
    """Find links to country-specific twin city sub-pages."""
    subpages = []
    content = soup.find('div', {'class': 'mw-parser-output'})
    if not content:
        return subpages

    for a in content.find_all('a', href=True):
        href = a['href']
        if '/wiki/List_of_twin_towns_and_sister_cities_in_' in href:
            continental = ['in_Europe', 'in_North_America', 'in_South_America',
                           'in_Asia', 'in_Africa', 'in_Oceania']
            if not any(c in href for c in continental):
                full_url = 'https://en.wikipedia.org' + href if href.startswith('/') else href
                # Normalize URL (remove anchors)
                full_url = full_url.split('#')[0]
                if full_url not in subpages:
                    subpages.append(full_url)
    return subpages

def extract_pairs_from_country_page(soup, page_country):
    """Extract twin city pairs from a country-specific page.

    Strategy: Find every div-col and ul that contains twin city lists,
    then use find_previous('p') to find the host city name.
    Most content is nested inside <link> template style elements,
    so we can't just iterate direct children.
    """
    pairs = []
    content = soup.find('div', {'class': 'mw-parser-output'})
    if not content:
        return pairs

    # Find the "See also" or "References" heading to know where to stop
    stop_headings = {'see also', 'references', 'external links', 'notes', 'bibliography'}
    stop_element = None
    for heading_div in content.find_all('div', {'class': 'mw-heading'}):
        h = heading_div.find(['h2', 'h3'])
        if h and h.get_text(strip=True).lower().strip() in stop_headings:
            stop_element = heading_div
            break

    # Find all twin city lists (div-col containers and standalone ul)
    twin_lists = []

    # Strategy 1: All div-col elements
    for dc in content.find_all('div', {'class': 'div-col'}):
        if stop_element and dc.sourceline and stop_element.sourceline:
            if dc.sourceline > stop_element.sourceline:
                continue
        twin_lists.append(dc)

    # Strategy 2: Also find <ul> elements that are direct children or inside link elements
    # but NOT inside div-col (to avoid double counting)
    for ul in content.find_all('ul'):
        # Skip if inside a div-col (already handled)
        if ul.find_parent('div', {'class': 'div-col'}):
            continue
        # Skip if inside nav/toc elements
        if ul.find_parent('div', {'class': ['toc', 'hlist', 'horizontal-toc', 'navbox']}):
            continue
        if ul.find_parent('nav'):
            continue
        if stop_element and ul.sourceline and stop_element.sourceline:
            if ul.sourceline > stop_element.sourceline:
                continue

        # Check if items look like twin cities (have flag icons or city links)
        items = ul.find_all('li', recursive=False)
        if not items:
            continue

        # Heuristic: twin city items usually have flagicon spans or city links
        has_flag = any(li.find('span', {'class': 'flagicon'}) for li in items[:3])
        has_wiki_link = any(li.find('a', href=re.compile(r'^/wiki/')) for li in items[:3])

        if has_flag or (has_wiki_link and len(items) <= 50):
            # Check if the preceding paragraph looks like a city name
            prev_p = ul.find_previous('p')
            if prev_p:
                p_text = prev_p.get_text(strip=True)
                p_link = prev_p.find('a', href=re.compile(r'^/wiki/'))
                if p_link and len(p_text) < 200:
                    twin_lists.append(ul)

    # Now extract pairs from each twin list
    seen_lists = set()
    for twin_list in twin_lists:
        # Deduplicate by id
        list_id = id(twin_list)
        if list_id in seen_lists:
            continue
        seen_lists.add(list_id)

        # Find the host city from the preceding <p> tag
        prev_p = twin_list.find_previous('p')
        if not prev_p:
            continue

        # Extract city name from the paragraph
        host_city = None
        for a in prev_p.find_all('a'):
            href = a.get('href', '')
            if href.startswith('#'):
                continue
            link_text = a.get_text(strip=True)
            if link_text and len(link_text) > 1:
                host_city = re.sub(r'\[.*?\]', '', link_text).strip()
                break

        if not host_city:
            continue

        # Extract twin cities from the list
        if twin_list.name == 'div':
            items = twin_list.find_all('li')
        else:
            items = twin_list.find_all('li', recursive=False)

        for li in items:
            twin = parse_twin_city(li)
            if twin:
                twin_city, twin_country = twin
                pairs.append({
                    'city1': host_city,
                    'country1': page_country,
                    'city2': twin_city,
                    'country2': twin_country
                })

    return pairs

def parse_twin_city(li):
    """Parse a list item to extract twin city name and country."""
    text = li.get_text(strip=True)
    if not text or len(text) < 2:
        return None

    # Clean text of citation markers
    text = re.sub(r'\[.*?\]', '', text).strip()
    if not text:
        return None

    # Get city name from first meaningful link
    city_name = None
    for a in li.find_all('a'):
        href = a.get('href', '')
        if href.startswith('#'):
            continue
        link_text = a.get_text(strip=True)
        if link_text and len(link_text) > 1:
            city_name = link_text
            break

    if not city_name:
        # Fall back to text parsing
        parts = text.split(',')
        if parts:
            city_name = parts[0].strip()

    if not city_name or len(city_name) < 2:
        return None

    # Extract country - text after city name
    country = ""
    idx = text.find(city_name)
    if idx >= 0:
        after = text[idx + len(city_name):]
        after = re.sub(r'^[\s,]+', '', after)
        if after:
            country = after.strip()
            country = re.sub(r'\(.*?\)', '', country).strip()
            country = country.rstrip(',').strip()

    return (city_name.strip(), country)

def main():
    continental_urls = [
        "https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Europe",
        "https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_North_America",
        "https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_South_America",
        "https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Asia",
        "https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Africa",
        "https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Oceania",
    ]

    all_subpage_urls = set()

    # Step 1: Collect all country sub-page URLs from continental pages
    for url in continental_urls:
        print(f"Scanning continental page: {url.split('/')[-1].replace('_', ' ')}")
        try:
            soup = get_page(url)
            subpages = extract_country_subpage_urls(soup)
            print(f"  Found {len(subpages)} country sub-pages")
            all_subpage_urls.update(subpages)
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nTotal unique country sub-pages: {len(all_subpage_urls)}")

    # Step 2: Scrape each country sub-page
    all_pairs = []
    for i, url in enumerate(sorted(all_subpage_urls)):
        page_name = url.split('/')[-1].replace('_', ' ')
        print(f"[{i+1}/{len(all_subpage_urls)}] Scraping: {page_name}")
        try:
            soup = get_page(url)
            country = get_country_from_title(soup)
            pairs = extract_pairs_from_country_page(soup, country)
            print(f"  Country: {country}, Pairs: {len(pairs)}")
            all_pairs.extend(pairs)
        except Exception as e:
            print(f"  Error: {e}")

    # Step 3: Deduplicate
    cleaned = []
    seen = set()
    for p in all_pairs:
        c1 = re.sub(r'\[.*?\]', '', p['city1']).strip()
        c2 = re.sub(r'\[.*?\]', '', p['city2']).strip()
        co1 = re.sub(r'\[.*?\]', '', p['country1']).strip()
        co2 = re.sub(r'\[.*?\]', '', p['country2']).strip()

        if not c1 or not c2 or len(c1) < 2 or len(c2) < 2:
            continue

        key = tuple(sorted([(c1, co1), (c2, co2)]))
        if key not in seen:
            seen.add(key)
            cleaned.append({
                'city1': c1,
                'country1': co1,
                'city2': c2,
                'country2': co2
            })

    print(f"\nTotal unique pairs: {len(cleaned)}")

    # Save to CSV
    csv_path = '/Users/hekman/Desktop/Code/twincities/twin_cities_raw.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['city1', 'country1', 'city2', 'country2'])
        writer.writeheader()
        writer.writerows(cleaned)

    print(f"Saved to {csv_path}")

    # Print some stats per country
    from collections import Counter
    country_counts = Counter()
    for p in cleaned:
        country_counts[p['country1']] += 1
    print("\nTop 20 countries by pairs:")
    for country, count in country_counts.most_common(20):
        print(f"  {country}: {count}")

if __name__ == '__main__':
    main()
