# Twin Cities

An interactive world map visualizing **25,900+ sister/twin city partnerships** across the globe.

Twin cities (or sister cities) are a form of legal agreement between towns, cities, regions, or countries for the purpose of promoting cultural and commercial ties. This project scrapes, geocodes, and visualizes these connections on a dark-themed interactive map.

**Made by Erik Hekman with [Claude Code](https://claude.ai/claude-code)**

## Features

- **Interactive world map** with 25,900+ sister city connections rendered as lines between cities
- **Click to select** a city and see all its sister city connections highlighted, with labels on each connected city
- **Hover** over any city dot to see its connections and a tooltip with details
- **Search** cities or countries — matching cities are labeled on the map
- **Zoom & pan** — scroll to zoom, drag to pan, or use the on-screen controls
- **Dark mode** design with transparent connection lines

## How It Was Built

### 1. Data Collection (Python + BeautifulSoup)

Sister city data was scraped from six Wikipedia pages covering all continents:

- [Europe](https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Europe)
- [North America](https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_North_America)
- [South America](https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_South_America)
- [Asia](https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Asia)
- [Africa](https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Africa)
- [Oceania](https://en.wikipedia.org/wiki/List_of_twin_towns_and_sister_cities_in_Oceania)

Each continental page links to country-specific sub-pages (81 in total). The scraper follows these links and parses the HTML structure — which turned out to be tricky because Wikipedia wraps most content inside `<link>` template-style elements, making direct child iteration miss ~98% of the data. The fix was using `find_all` on the full content div and `find_previous('p')` to associate twin city lists with their host city.

**Result:** 26,114 unique city pairs from 81 country pages.

### 2. Geocoding (Wikipedia API + Nominatim)

With 17,820 unique cities to geocode, a multi-phase approach was used:

1. **Wikipedia API** (batch 50 titles per request) — fast, found ~12,000 cities
2. **Wikipedia search retry** — caught cities with slightly different article names
3. **Nominatim fallback** — for the remaining top 3,000 most-referenced cities

This initial pass achieved 91.6% coverage (23,912 pairs). A second targeted pass was then run to recover the remaining ~2,400 missing cities using:

4. **Name cleaning** — stripping parenthetical qualifiers like "(rural gmina)", splitting compound names like "Haaren -- Esch", and fixing country names like "Georgia (country)"
5. **Wikipedia search + Nominatim** — combining search-based lookups with cleaned name variants

**Result:** 25,917 pairs geocoded (99.2% coverage) — only 197 pairs remain unresolved.

### 3. Visualization (React + TypeScript)

The frontend is built with React, TypeScript, and react-simple-maps. Key technical decisions:

- **Single SVG `<path>` for all 24K lines** — rendering individual `<Line>` components for each connection crashed the browser. Collapsing all lines into one SVG path string reduced DOM nodes from ~48,000 to 1.
- **`useMemo` everywhere** — all heavy computations (line paths, city nodes, label positions) are memoized to keep the UI responsive.
- **Debounced search** (300ms) — prevents re-filtering 24K pairs on every keystroke.
- **Smart marker filtering** — only cities with 3+ connections are shown by default to avoid visual noise; all cities appear when searching.
- **Label collision detection** — when selecting a city, labels are placed using an 8-position algorithm (right, left, above, below, and diagonal offsets) with fallback stacking to avoid overlaps.
- **d3-geo projection** — `geoMercator` is used directly to compute SVG coordinates for the single-path rendering approach.

## Tech Stack

- **Data collection:** Python, BeautifulSoup, requests
- **Geocoding:** Wikipedia API, geopy/Nominatim
- **Frontend:** React, TypeScript, react-simple-maps, d3-geo, papaparse
- **Styling:** CSS with dark theme

## Project Structure

```
twincities/
├── scrape_twin_cities.py      # Wikipedia scraper
├── geocode_cities.py           # Multi-phase geocoder
├── twin_cities_raw.csv         # Raw scraped data (26K pairs)
├── README.md
└── app/                        # React application
    ├── public/
    │   └── twin_cities.csv     # Geocoded data (24K pairs)
    └── src/
        ├── App.tsx             # Main application component
        └── App.css             # Dark theme styles
```

## Running Locally

```bash
# Install dependencies
cd app
npm install --legacy-peer-deps

# Start development server
npm start
```

The app runs on `http://localhost:3000` by default.

## Data Format

The CSV file (`twin_cities.csv`) contains one row per sister city pair:

| Column   | Description                    |
|----------|--------------------------------|
| city1    | First city name                |
| country1 | Country of first city          |
| lat1     | Latitude of first city         |
| lng1     | Longitude of first city        |
| city2    | Second city name               |
| country2 | Country of second city         |
| lat2     | Latitude of second city        |
| lng2     | Longitude of second city       |

## License

MIT
