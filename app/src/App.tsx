import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
} from "react-simple-maps";
import { geoMercator } from "d3-geo";
import Papa from "papaparse";
import "./App.css";

const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

interface CityPair {
  city1: string;
  country1: string;
  lat1: number;
  lng1: number;
  city2: string;
  country2: string;
  lat2: number;
  lng2: number;
}

interface CityNode {
  name: string;
  country: string;
  coords: [number, number];
  connections: number;
}

function App() {
  const [pairs, setPairs] = useState<CityPair[]>([]);
  const [showModal, setShowModal] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [hoveredCity, setHoveredCity] = useState<{
    city: CityNode;
    pairs: CityPair[];
    x: number;
    y: number;
  } | null>(null);
  const [selectedCity, setSelectedCity] = useState<{
    city: CityNode;
    pairs: CityPair[];
  } | null>(null);

  // Zoom & Pan state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<[number, number]>([0, 0]);
  const [isPanning, setIsPanning] = useState(false);
  const isDragging = useRef(false);
  const panStart = useRef<[number, number]>([0, 0]);
  const panOrigin = useRef<[number, number]>([0, 0]);
  const mapContainerRef = useRef<HTMLDivElement>(null);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.85 : 1.18;
      setZoom((z) => Math.min(Math.max(z * delta, 0.5), 20));
    },
    []
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button === 0 || e.button === 1) {
        setIsPanning(true);
        isDragging.current = false;
        panStart.current = [e.clientX, e.clientY];
        panOrigin.current = pan;
      }
    },
    [pan]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isPanning) return;
      const dx = e.clientX - panStart.current[0];
      const dy = e.clientY - panStart.current[1];
      // Only start dragging after 3px threshold
      if (!isDragging.current && Math.abs(dx) + Math.abs(dy) < 3) return;
      isDragging.current = true;
      const container = mapContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const scaleX = 960 / rect.width;
      const scaleY = 500 / rect.height;
      setPan([panOrigin.current[0] + dx * scaleX, panOrigin.current[1] + dy * scaleY]);
    },
    [isPanning]
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
    // Reset isDragging after a short delay so the click event
    // (which fires after mouseup) can still check it
    setTimeout(() => {
      isDragging.current = false;
    }, 0);
  }, []);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan([0, 0]);
  }, []);

  const zoomIn = useCallback(() => {
    setZoom((z) => Math.min(z * 1.4, 20));
  }, []);

  const zoomOut = useCallback(() => {
    setZoom((z) => Math.max(z * 0.7, 0.5));
  }, []);

  // Load CSV data
  useEffect(() => {
    fetch(process.env.PUBLIC_URL + "/twin_cities.csv")
      .then((res) => res.text())
      .then((csvText) => {
        const result = Papa.parse<CityPair>(csvText, {
          header: true,
          dynamicTyping: true,
          skipEmptyLines: true,
        });
        setPairs(
          result.data.filter((p) => p.lat1 && p.lng1 && p.lat2 && p.lng2)
        );
      });
  }, []);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm), 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Filter pairs based on search
  const filteredPairs = useMemo(() => {
    if (!debouncedSearch) return pairs;
    const lower = debouncedSearch.toLowerCase();
    return pairs.filter(
      (p) =>
        (p.city1 || "").toLowerCase().includes(lower) ||
        (p.city2 || "").toLowerCase().includes(lower) ||
        (p.country1 || "").toLowerCase().includes(lower) ||
        (p.country2 || "").toLowerCase().includes(lower)
    );
  }, [pairs, debouncedSearch]);

  // Build city nodes from filtered pairs
  const { cities, cityMap } = useMemo(() => {
    const map = new Map<string, CityNode>();
    filteredPairs.forEach((p) => {
      const key1 = `${p.lat1}|${p.lng1}`;
      const key2 = `${p.lat2}|${p.lng2}`;
      if (!map.has(key1)) {
        map.set(key1, {
          name: p.city1,
          country: p.country1 || "",
          coords: [p.lng1, p.lat1],
          connections: 0,
        });
      }
      map.get(key1)!.connections++;
      if (!map.has(key2)) {
        map.set(key2, {
          name: p.city2,
          country: p.country2 || "",
          coords: [p.lng2, p.lat2],
          connections: 0,
        });
      }
      map.get(key2)!.connections++;
    });
    return { cities: Array.from(map.values()), cityMap: map };
  }, [filteredPairs]);

  // Total city count (unfiltered) for modal
  const totalCities = useMemo(() => {
    const set = new Set<string>();
    pairs.forEach((p) => {
      set.add(`${p.lat1}|${p.lng1}`);
      set.add(`${p.lat2}|${p.lng2}`);
    });
    return set.size;
  }, [pairs]);

  // Projection
  const projection = useMemo(
    () =>
      geoMercator()
        .scale(140)
        .center([10, 30])
        .translate([960 / 2, 500 / 2]),
    []
  );

  // Build a single SVG path for ALL connection lines
  const linesPath = useMemo(() => {
    const segments: string[] = [];
    filteredPairs.forEach((p) => {
      const from = projection([p.lng1, p.lat1]);
      const to = projection([p.lng2, p.lat2]);
      if (from && to) {
        segments.push(`M${from[0]},${from[1]}L${to[0]},${to[1]}`);
      }
    });
    return segments.join("");
  }, [filteredPairs, projection]);

  const isFiltered = debouncedSearch.length > 0;

  // Find pairs for a city
  const findPairsForCity = useCallback(
    (city: CityNode) => {
      return filteredPairs.filter(
        (p) =>
          (p.lng1 === city.coords[0] && p.lat1 === city.coords[1]) ||
          (p.lng2 === city.coords[0] && p.lat2 === city.coords[1])
      );
    },
    [filteredPairs]
  );

  // Highlighted lines path for selected city
  const selectedPath = useMemo(() => {
    if (!selectedCity) return "";
    const segments: string[] = [];
    selectedCity.pairs.forEach((p) => {
      const from = projection([p.lng1, p.lat1]);
      const to = projection([p.lng2, p.lat2]);
      if (from && to) {
        segments.push(`M${from[0]},${from[1]}L${to[0]},${to[1]}`);
      }
    });
    return segments.join("");
  }, [selectedCity, projection]);

  // Highlighted lines path for hovered city (independent of selection)
  const hoveredPath = useMemo(() => {
    if (!hoveredCity) return "";
    const segments: string[] = [];
    hoveredCity.pairs.forEach((p) => {
      const from = projection([p.lng1, p.lat1]);
      const to = projection([p.lng2, p.lat2]);
      if (from && to) {
        segments.push(`M${from[0]},${from[1]}L${to[0]},${to[1]}`);
      }
    });
    return segments.join("");
  }, [hoveredCity, projection]);

  // Compute selected city's connected city nodes (for rendering labels + dots)
  const selectedConnectedCities = useMemo(() => {
    if (!selectedCity) return [];
    const connected: { name: string; country: string; projected: [number, number]; labelX: number; labelY: number }[] = [];
    // Add the selected city itself
    const selfProj = projection(selectedCity.city.coords);
    if (selfProj) {
      connected.push({
        name: selectedCity.city.name,
        country: selectedCity.city.country,
        projected: [selfProj[0], selfProj[1]],
        labelX: selfProj[0] + 7,
        labelY: selfProj[1] - 8,
      });
    }
    // Add each twin
    selectedCity.pairs.forEach((p) => {
      const isCity1 =
        p.lng1 === selectedCity.city.coords[0] &&
        p.lat1 === selectedCity.city.coords[1];
      const twinCoords: [number, number] = isCity1
        ? [p.lng2, p.lat2]
        : [p.lng1, p.lat1];
      const twinName = isCity1 ? p.city2 : p.city1;
      const twinCountry = isCity1 ? p.country2 || "" : p.country1 || "";
      const proj = projection(twinCoords);
      if (proj) {
        connected.push({
          name: twinName,
          country: twinCountry,
          projected: [proj[0], proj[1]],
          labelX: proj[0] + 7,
          labelY: proj[1] - 8,
        });
      }
    });

    // Resolve label overlaps by nudging labels to new positions
    const placedRects: { x: number; y: number; w: number; h: number; idx: number }[] = [];
    const lh = 15;
    const pad = 2; // padding between labels

    for (let i = 0; i < connected.length; i++) {
      const c = connected[i];
      const lw = c.name.length * 5.5 + 14;
      let bestX = c.labelX;
      let bestY = c.labelY;
      let resolved = false;

      // Try a set of candidate positions around the dot
      const offsets = [
        [7, -8],           // right-top (default)
        [7, 6],            // right-bottom
        [-lw - 5, -8],     // left-top
        [-lw - 5, 6],      // left-bottom
        [7, -8 - lh - pad],  // right, further up
        [7, 6 + lh + pad],   // right, further down
        [-lw - 5, -8 - lh - pad], // left, further up
        [-lw - 5, 6 + lh + pad],  // left, further down
      ];

      for (const [ox, oy] of offsets) {
        const cx = c.projected[0] + ox;
        const cy = c.projected[1] + oy;
        const overlaps = placedRects.some(
          (r) => cx < r.x + r.w + pad && cx + lw + pad > r.x && cy < r.y + r.h + pad && cy + lh + pad > r.y
        );
        if (!overlaps) {
          bestX = cx;
          bestY = cy;
          resolved = true;
          break;
        }
      }

      // If all 8 positions overlap, try stacking further down
      if (!resolved) {
        for (let dy = 0; dy < 200; dy += lh + pad) {
          const cx = c.projected[0] + 7;
          const cy = c.projected[1] + dy;
          const overlaps = placedRects.some(
            (r) => cx < r.x + r.w + pad && cx + lw + pad > r.x && cy < r.y + r.h + pad && cy + lh + pad > r.y
          );
          if (!overlaps) {
            bestX = cx;
            bestY = cy;
            break;
          }
        }
      }

      c.labelX = bestX;
      c.labelY = bestY;
      placedRects.push({ x: bestX, y: bestY, w: lw, h: lh, idx: i });
    }

    return connected;
  }, [selectedCity, projection]);

  const hasSelection = selectedCity !== null;

  // Compute labels for search results (all filtered cities get labels)
  const searchLabels = useMemo(() => {
    if (!isFiltered || hasSelection) return [];
    const labels: { name: string; country: string; projected: [number, number]; labelX: number; labelY: number }[] = [];
    cities.forEach((city) => {
      const proj = projection(city.coords);
      if (proj) {
        labels.push({
          name: city.name,
          country: city.country,
          projected: [proj[0], proj[1]],
          labelX: proj[0] + 7,
          labelY: proj[1] - 8,
        });
      }
    });

    // Resolve label overlaps
    const placedRects: { x: number; y: number; w: number; h: number }[] = [];
    const lh = 15;
    const pad = 2;

    for (const c of labels) {
      const lw = c.name.length * 5.5 + 14;
      let bestX = c.labelX;
      let bestY = c.labelY;
      let resolved = false;

      const offsets = [
        [7, -8],
        [7, 6],
        [-lw - 5, -8],
        [-lw - 5, 6],
        [7, -8 - lh - pad],
        [7, 6 + lh + pad],
        [-lw - 5, -8 - lh - pad],
        [-lw - 5, 6 + lh + pad],
      ];

      for (const [ox, oy] of offsets) {
        const cx = c.projected[0] + ox;
        const cy = c.projected[1] + oy;
        const overlaps = placedRects.some(
          (r) => cx < r.x + r.w + pad && cx + lw + pad > r.x && cy < r.y + r.h + pad && cy + lh + pad > r.y
        );
        if (!overlaps) {
          bestX = cx;
          bestY = cy;
          resolved = true;
          break;
        }
      }

      if (!resolved) {
        for (let dy = 0; dy < 200; dy += lh + pad) {
          const cx = c.projected[0] + 7;
          const cy = c.projected[1] + dy;
          const overlaps = placedRects.some(
            (r) => cx < r.x + r.w + pad && cx + lw + pad > r.x && cy < r.y + r.h + pad && cy + lh + pad > r.y
          );
          if (!overlaps) {
            bestX = cx;
            bestY = cy;
            break;
          }
        }
      }

      c.labelX = bestX;
      c.labelY = bestY;
      placedRects.push({ x: bestX, y: bestY, w: lw, h: lh });
    }

    return labels;
  }, [isFiltered, cities, projection, hasSelection]);

  // Click handler for city dots
  const handleCityClick = useCallback(
    (city: CityNode) => {
      if (isDragging.current) return; // Ignore clicks after dragging
      if (selectedCity?.city === city) {
        setSelectedCity(null);
      } else {
        const cityPairs = findPairsForCity(city);
        setSelectedCity({ city, pairs: cityPairs });
      }
    },
    [selectedCity, findPairsForCity]
  );

  // Click on map background to deselect
  const handleMapClick = useCallback(() => {
    if (isDragging.current) return; // Ignore clicks after dragging
    if (selectedCity) {
      setSelectedCity(null);
    }
  }, [selectedCity]);

  return (
    <div className="app">
      {/* Info Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="modal-close"
              onClick={() => setShowModal(false)}
            >
              &times;
            </button>
            <h1>Twin Cities</h1>
            <h2>A Global Network of City Partnerships</h2>
            <p>
              Twin cities (or sister cities) are a form of legal agreement
              between towns, cities, regions, or countries for the purpose of
              promoting cultural and commercial ties.
            </p>
            <p>
              This visualization shows{" "}
              <strong>{pairs.length.toLocaleString()}</strong> sister city
              connections across the globe, sourced from Wikipedia. Each line
              represents a partnership between two cities.
            </p>
            <p className="modal-credit">Made by Erik Hekman with Claude Code</p>
            <div className="modal-stats">
              <div className="stat">
                <span className="stat-number">
                  {pairs.length.toLocaleString()}
                </span>
                <span className="stat-label">Connections</span>
              </div>
              <div className="stat">
                <span className="stat-number">
                  {totalCities.toLocaleString()}
                </span>
                <span className="stat-label">Cities</span>
              </div>
            </div>
            <div className="modal-buttons">
              <button className="modal-cta" onClick={() => setShowModal(false)}>
                Explore the Map
              </button>
              <a
                className="modal-github"
                href="https://github.com/hekman/twincities"
                target="_blank"
                rel="noopener noreferrer"
              >
                <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
                  <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
                </svg>
                View source on GitHub
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1 onClick={() => setShowModal(true)}>Twin Cities</h1>
          <span className="header-subtitle">
            {filteredPairs.length.toLocaleString()} connections &middot;{" "}
            {cityMap.size.toLocaleString()} cities
          </span>
        </div>
        <div className="header-right">
          <input
            type="text"
            placeholder="Search cities or countries..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setSelectedCity(null);
            }}
            className="search-input"
          />
          {searchTerm && (
            <button
              className="clear-btn"
              onClick={() => {
                setSearchTerm("");
                setSelectedCity(null);
              }}
              title="Clear search"
            >
              &times;
            </button>
          )}
          <button
            className="info-btn"
            onClick={() => setShowModal(true)}
            title="About"
          >
            ?
          </button>
        </div>
      </header>

      {/* Selected city info bar */}
      {selectedCity && (
        <div className="selection-bar">
          <div className="selection-info">
            <span className="selection-city">{selectedCity.city.name}</span>
            <span className="selection-country">
              {selectedCity.city.country}
            </span>
            <span className="selection-count">
              {selectedCity.pairs.length} sister{" "}
              {selectedCity.pairs.length === 1 ? "city" : "cities"}
            </span>
          </div>
          <button
            className="selection-close"
            onClick={() => setSelectedCity(null)}
          >
            &times; Clear selection
          </button>
        </div>
      )}

      {/* Map */}
      <div
        className="map-container"
        ref={mapContainerRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ cursor: isPanning ? "grabbing" : "default" }}
      >
        {/* Zoom controls */}
        <div className="zoom-controls">
          <button className="zoom-btn" onClick={zoomIn} title="Zoom in">+</button>
          <button className="zoom-btn" onClick={zoomOut} title="Zoom out">&minus;</button>
          <button className="zoom-btn zoom-reset" onClick={resetView} title="Reset view">⌂</button>
        </div>

        <ComposableMap
          projection="geoMercator"
          projectionConfig={{
            scale: 140,
            center: [10, 30],
          }}
          width={960}
          height={500}
          style={{ width: "100%", height: "100%" }}
        >
          {/* Clickable background rect to deselect */}
          <rect
            width={960}
            height={500}
            fill="transparent"
            onClick={handleMapClick}
          />

          <g transform={`translate(${480 + pan[0]}, ${250 + pan[1]}) scale(${zoom}) translate(${-480}, ${-250})`}>

          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rpidr}
                  geography={geo}
                  fill="#1a1a2e"
                  stroke="#2a2a4a"
                  strokeWidth={0.5}
                  style={{
                    default: { outline: "none" },
                    hover: { outline: "none", fill: "#222244" },
                    pressed: { outline: "none" },
                  }}
                  onClick={handleMapClick}
                />
              ))
            }
          </Geographies>

          {/* All connection lines as a single path */}
          <path
            d={linesPath}
            fill="none"
            stroke={
              hasSelection
                ? "rgba(0, 180, 255, 0.015)"
                : isFiltered
                ? "rgba(0, 180, 255, 0.3)"
                : "rgba(0, 180, 255, 0.08)"
            }
            strokeWidth={isFiltered && !hasSelection ? 1 : 0.5}
            strokeLinecap="round"
          />

          {/* Highlighted lines for selected city */}
          {selectedPath && (
            <path
              d={selectedPath}
              fill="none"
              stroke="rgba(0, 220, 255, 0.85)"
              strokeWidth={1.5}
              strokeLinecap="round"
            />
          )}

          {/* Highlighted lines for hovered city (shows on top, even during selection) */}
          {hoveredPath && (
            <path
              d={hoveredPath}
              fill="none"
              stroke="rgba(255, 200, 50, 0.7)"
              strokeWidth={1.5}
              strokeLinecap="round"
            />
          )}

          {/* City markers */}
          {(isFiltered ? cities : cities.filter((c) => c.connections >= 3)).map(
            (city, i) => {
              const projected = projection(city.coords);
              if (!projected) return null;

              const isSelected = selectedCity?.city === city;
              const isHovered = hoveredCity?.city === city;
              // Dim non-connected cities when there's a selection
              const isConnected =
                !hasSelection ||
                isSelected ||
                selectedConnectedCities.some(
                  (c) =>
                    Math.abs(c.projected[0] - projected[0]) < 0.1 &&
                    Math.abs(c.projected[1] - projected[1]) < 0.1
                );

              return (
                <circle
                  key={`m-${i}`}
                  cx={projected[0]}
                  cy={projected[1]}
                  r={
                    isSelected
                      ? 5
                      : isHovered
                      ? 4
                      : hasSelection && !isConnected
                      ? Math.min(1 + city.connections * 0.05, 1.5)
                      : Math.min(1 + city.connections * 0.15, 3)
                  }
                  fill={
                    isSelected
                      ? "#fff"
                      : isHovered
                      ? "rgba(255, 255, 255, 0.9)"
                      : hasSelection && !isConnected
                      ? "rgba(0, 200, 255, 0.04)"
                      : "rgba(0, 200, 255, 0.7)"
                  }
                  stroke={
                    isSelected
                      ? "rgba(0, 200, 255, 0.8)"
                      : hasSelection && !isConnected
                      ? "rgba(0, 200, 255, 0.02)"
                      : "rgba(0, 200, 255, 0.3)"
                  }
                  strokeWidth={isSelected ? 2 : 0.5}
                  style={{ cursor: "pointer" }}
                  onMouseEnter={(e) => {
                    const cityPairs = findPairsForCity(city);
                    setHoveredCity({
                      city,
                      pairs: cityPairs,
                      x: e.clientX,
                      y: e.clientY,
                    });
                  }}
                  onMouseLeave={() => setHoveredCity(null)}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCityClick(city);
                  }}
                />
              );
            }
          )}

          {/* Labels for selected city's connected cities */}
          {selectedConnectedCities.map((c, i) => (
            <g key={`label-${i}`}>
              {/* Bright dot for connected city */}
              <circle
                cx={c.projected[0]}
                cy={c.projected[1]}
                r={i === 0 ? 5 : 3.5}
                fill={i === 0 ? "#fff" : "rgba(0, 220, 255, 0.9)"}
                stroke={i === 0 ? "rgba(0, 200, 255, 0.8)" : "rgba(0, 220, 255, 0.4)"}
                strokeWidth={i === 0 ? 2 : 1}
              />
              {/* Leader line from dot to label if label was repositioned */}
              {(Math.abs(c.labelX - (c.projected[0] + 7)) > 1 || Math.abs(c.labelY - (c.projected[1] - 8)) > 1) && (
                <line
                  x1={c.projected[0]}
                  y1={c.projected[1]}
                  x2={c.labelX + 2}
                  y2={c.labelY + 7}
                  stroke="rgba(0, 180, 255, 0.15)"
                  strokeWidth={0.5}
                />
              )}
              {/* Label background */}
              <rect
                x={c.labelX}
                y={c.labelY}
                width={c.name.length * 5.5 + 14}
                height={15}
                rx={3}
                fill="rgba(13, 13, 26, 0.9)"
                stroke="rgba(0, 180, 255, 0.2)"
                strokeWidth={0.5}
              />
              {/* Label text */}
              <text
                x={c.labelX + 5}
                y={c.labelY + 11}
                fontSize={i === 0 ? 10 : 9}
                fontWeight={i === 0 ? 700 : 500}
                fill={i === 0 ? "#fff" : "rgba(0, 220, 255, 0.9)"}
                fontFamily="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
              >
                {c.name}
              </text>
            </g>
          ))}

          {/* Labels for search results */}
          {searchLabels.map((c, i) => (
            <g key={`search-label-${i}`}>
              {/* Leader line if repositioned */}
              {(Math.abs(c.labelX - (c.projected[0] + 7)) > 1 || Math.abs(c.labelY - (c.projected[1] - 8)) > 1) && (
                <line
                  x1={c.projected[0]}
                  y1={c.projected[1]}
                  x2={c.labelX + 2}
                  y2={c.labelY + 7}
                  stroke="rgba(0, 180, 255, 0.15)"
                  strokeWidth={0.5}
                />
              )}
              <rect
                x={c.labelX}
                y={c.labelY}
                width={c.name.length * 5.5 + 14}
                height={15}
                rx={3}
                fill="rgba(13, 13, 26, 0.9)"
                stroke="rgba(0, 180, 255, 0.2)"
                strokeWidth={0.5}
              />
              <text
                x={c.labelX + 5}
                y={c.labelY + 11}
                fontSize={9}
                fontWeight={500}
                fill="rgba(0, 220, 255, 0.9)"
                fontFamily="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
              >
                {c.name}
              </text>
            </g>
          ))}

          </g>
        </ComposableMap>
      </div>

      {/* Tooltip (always shows on hover) */}
      {hoveredCity && (
        <div
          className="tooltip"
          style={{
            left: Math.min(hoveredCity.x + 15, window.innerWidth - 280),
            top: Math.min(hoveredCity.y - 10, window.innerHeight - 200),
          }}
        >
          <div className="tooltip-header">
            <div className="tooltip-city">{hoveredCity.city.name}</div>
            <div className="tooltip-country">{hoveredCity.city.country}</div>
          </div>
          <div className="tooltip-divider" />
          <div className="tooltip-label">
            {hoveredCity.pairs.length} sister{" "}
            {hoveredCity.pairs.length === 1 ? "city" : "cities"}:
          </div>
          <div className="tooltip-list">
            {hoveredCity.pairs.slice(0, 8).map((p, i) => {
              const isCity1 =
                p.lng1 === hoveredCity.city.coords[0] &&
                p.lat1 === hoveredCity.city.coords[1];
              const twinName = isCity1 ? p.city2 : p.city1;
              const twinCountry = isCity1
                ? p.country2 || ""
                : p.country1 || "";
              return (
                <div key={i} className="tooltip-twin">
                  {twinName}
                  {twinCountry && (
                    <span className="tooltip-twin-country">
                      , {twinCountry}
                    </span>
                  )}
                </div>
              );
            })}
            {hoveredCity.pairs.length > 8 && (
              <div className="tooltip-more">
                +{hoveredCity.pairs.length - 8} more
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
