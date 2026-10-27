// The map under Your districts, always shown: a street map with each district's outline, the
// election precinct's too, and the address as a pin, centred on the pin. Leaflet (vendor/leaflet, imported once there's a
// ballot) draws it; the street map's tiles come from OpenStreetMap through Pallot (/api/tiles),
// and the outlines from /api/district-outlines. A row of buttons right above the map, one per
// district, is its legend: picking one, or its line on the map, highlights it and zooms to it;
// picking it again, or the map's pin button, goes back to the address. The scroll wheel only
// zooms once the map has been clicked, and on a touch screen the map moves with two fingers, so
// it never traps the page's scrolling. Its heading folds it away like a race's, remembered in
// the browser (view.js, showMap: folded at first); nothing is fetched for it while it's folded.
// A change of the switch elsewhere (Settings, another tab) applies with syncMapShown().
// Every state's districts the ballot shows are outlined (outside Texas, asked with the state);
// the SBOE district and the election precinct are Texas's alone. With no district known it's the
// street map alone, with the pin, and nothing is asked of /api/district-outlines; with the street
// map off too, there's no map.

import { api } from "./api.js";
import { h, svg } from "./dom.js";
import { icon } from "./icons.js";
import { coverageOf, districtName as kindName, houseText } from "./labels.js";
import { setViewPref, viewPref } from "./view.js";

const KINDS = ["cd", "sd", "hd", "sboe"]; // then the election precinct, asked by its map's code and county
const REGIONS = [ // as far as the server serves tiles (sources/osm_tiles.py)
  [[22.5, -127], [51, -64]],
  [[50, -180], [72.5, -128]],
  [[50, 172], [54, 180]],
  [[18, -162], [23, -154]],
];
const STREET_ONLY = { outlines: [], notes: [], street_map: true };
const HOME_ZOOM = [10, 14]; // the view around the address: streets, and the nearest district if it fits
const TILES = "/api/tiles/{z}/{x}/{y}.png";
const OSM_CREDIT = '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';
const LEAFLET_CREDIT = '<a href="https://leafletjs.com" target="_blank" rel="noopener noreferrer">Leaflet</a>';
const touch = matchMedia("(pointer: coarse)").matches;
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

let section = null; // #district-map, found on the first ballot
const fetched = new Map(); // query -> the API's answer
let leaflet = null; // the import of Leaflet, once started
let L = null;
let map = null;
let tiles = null;
let pin = null;
let lines = new Map(); // kind -> { halo, line } on the map
let parts = null; // the panel's toggle, body, picks, canvas, notes and foot, made once
let shown = false; // the map is open (folded at first)
let drawn = ""; // the query whose outlines are on the map
let ballot = null;
let query = ""; // "cd=10&sd=14&hd=49&sboe=5&election_precinct=0300&county=453": the ballot's districts, or "@lat,lon" for the street map alone
let highlight = null; // the kind picked
let data = null; // the outlines for ``query``, once loaded
let failed = null; // why they couldn't be loaded
let pending = null; // the AbortController of the request still running

const streetOnly = () => query.startsWith("@");

// The box of REGIONS the address is in, which bounds the map and its tiles.
function regionOf({ lat, lon }) {
  return REGIONS.find(([[south, west], [north, east]]) => lat >= south && lat <= north && lon >= west && lon <= east)
    || REGIONS[0];
}

// The labels of a district on the map: its kind in the state's words, and its number ("At large").
function kindLabel(kind, size) {
  return kind === "election_precinct" ? "Precinct" : kindName(kind, coverageOf(ballot).labels, size);
}

function numberText(kind, number) {
  return kind === "cd" ? houseText(number, ballot.location.state) : String(number);
}

function districtName(kind, number) {
  if (kind === "election_precinct") return `Precinct ${number}`;
  return kind === "cd" && number === 0 ? `${kindLabel(kind, "long")} (${numberText(kind, number)})`
    : `${kindLabel(kind, "long")} District ${number}`;
}

// A short line in the district's colour and dash.
function swatch(kind) {
  return svg("svg", { class: "map-swatch", viewBox: "0 0 16 8", "aria-hidden": "true", focusable: "false" },
    svg("line", { class: ["map-outline", kind], x1: "1", y1: "4", x2: "15", y2: "4" }));
}

// After every render of the ballot: new districts load their outlines and go back to the
// address; a precinct update keeps the map where the voter left it.
export function syncMap(next) {
  ballot = next;
  if (!section) {
    section = document.querySelector("#district-map");
    new ResizeObserver(() => map?.invalidateSize()).observe(section);
  }
  const districts = next.districts || {};
  const kinds = coverageOf(next).districts;
  const asked = KINDS.filter((kind) => kinds.includes(kind) && districts[kind] != null && districts[kind] !== "")
    .map((kind) => [kind, districts[kind]]);
  const precinct = districts.election_precinct;
  if (precinct) asked.push(["election_precinct", precinct.code], ["county", precinct.county]);
  const { lat, lon, state } = next.location;
  if (asked.length && state && state !== "TX") asked.push(["state", state]);
  const placed = lat != null; // not a voter card the map couldn't place
  const nextQuery = !placed ? ""
    : asked.length ? new URLSearchParams(asked).toString()
      : next.street_map !== false ? `@${lat},${lon}` : "";
  section.hidden = !nextQuery;
  if (!nextQuery) {
    query = "";
    return;
  }
  makePanel();
  labelPanel(nextQuery.startsWith("@"));
  if (nextQuery !== query) {
    query = nextQuery;
    highlight = null;
    data = null;
    failed = null;
    if (shown) load();
    else pending?.abort();
  } else {
    placePin();
  }
}

// After the showMap switch changes: opens or folds the map to match.
export function syncMapShown() {
  if (parts && shown !== viewPref("showMap")) setShown(viewPref("showMap"));
}

function setShown(open) {
  shown = open;
  parts.body.hidden = !open;
  section.classList.toggle("collapsed", !open);
  parts.toggle.setAttribute("aria-expanded", String(open));
  if (!open || drawn === query) return;
  if (data || failed) draw();
  else if (!pending) load();
}

function pickDistrict(kind) {
  highlight = highlight === kind ? null : kind;
  for (const button of parts.picks.querySelectorAll("[data-map-kind]")) {
    button.setAttribute("aria-pressed", String(button.dataset.mapKind === highlight));
  }
  styleLines();
  fitView();
  parts.canvas.scrollIntoView({ block: "nearest" });
}

function makePanel() {
  if (parts) return;
  shown = viewPref("showMap");
  parts = {
    toggle: h("button", {
      type: "button", class: "map-toggle", "aria-expanded": String(shown), "aria-controls": "district-map-body",
      on: { click: () => {
        setShown(!shown);
        setViewPref("showMap", shown);
      } },
    }, h("span", { class: "chevron", "aria-hidden": "true" })),
    title: document.createTextNode(""),
    body: h("div", { id: "district-map-body", hidden: !shown }),
    hint: h("p", { class: "map-hint" }),
    picks: h("div", { class: "map-picks", role: "group", "aria-label": "Highlight a district on the map" }),
    canvas: h("div", { class: "map-canvas", role: "region" }),
    notes: h("div", { class: "map-notes" }),
    foot: h("p", { class: "fine map-foot" }),
  };
  parts.toggle.append(parts.title);
  parts.body.append(
    parts.hint,
    parts.picks,
    parts.canvas,
    parts.notes,
    parts.foot,
  );
  section.classList.toggle("collapsed", !shown);
  section.replaceChildren(h("h2", { id: "district-map-title" }, parts.toggle), parts.body);
}

// The heading, hint and name of the map: of the districts, or of the address alone.
function labelPanel(alone) {
  const move = touch ? "Move the map with two fingers." : "Click the map to zoom it with the scroll wheel.";
  parts.title.data = alone ? "Map of your address" : "Map of your districts";
  parts.hint.textContent = alone ? move
    : `Pick a district to highlight it and zoom to it; pick it again to go back to your address. ${move}`;
  parts.picks.hidden = alone;
  parts.canvas.setAttribute("aria-label", `Street map ${alone ? "" : "of your districts, "}centered on your address. `
    + "Arrow keys move it; + and − zoom.");
}

async function load() {
  failed = null;
  pending?.abort();
  const controller = new AbortController();
  pending = controller;
  const asked = query;
  parts.picks.replaceChildren();
  parts.notes.replaceChildren(h("p", { class: "district-note", role: "status" },
    streetOnly() ? "Loading the map…" : "Loading the district outlines…"));
  try {
    leaflet ||= import("../vendor/leaflet/leaflet-src.esm.js");
    const [module, got] = await Promise.all([
      leaflet,
      streetOnly() ? STREET_ONLY
        : fetched.get(asked) || api.get(`/api/district-outlines?${asked}`, { signal: controller.signal }),
    ]);
    if (controller.signal.aborted || !got) return;
    L = module;
    fetched.set(asked, got);
    if (asked !== query) return;
    data = got;
  } catch (error) {
    if (error.name === "AbortError") return;
    if (asked === query) failed = error.message;
  } finally {
    if (pending === controller) pending = null;
  }
  if (shown) draw(); // hidden meanwhile: drawn when it's shown, at its real size
}

function draw() {
  if (failed) {
    const retry = h("button", { type: "button", class: "link-btn", on: { click: load } }, "Try again");
    parts.notes.replaceChildren(h("p", { class: "district-warn" }, `Couldn't load the map: ${failed} `, retry));
    return;
  }
  drawn = query;
  const region = regionOf(ballot.location);
  makeMap(region);
  map.setMaxBounds(region);
  if (tiles && (!data.street_map || tiles.options.bounds !== region)) {
    tiles.remove();
    tiles = null;
  }
  if (data.street_map && !tiles) {
    tiles = L.tileLayer(TILES, {
      minZoom: 5, maxZoom: 18, bounds: region, attribution: OSM_CREDIT, className: "map-tiles",
    }).addTo(map);
  }
  for (const { halo, line } of lines.values()) {
    halo.remove();
    line.remove();
  }
  lines = new Map(data.outlines.map((outline) => {
    const rings = outline.rings.map((ring) => ring.map(([lon, lat]) => [lat, lon]));
    // the halo, wider than the line, keeps it readable over the streets and is what the pointer hits
    const halo = L.polygon(rings, { className: "map-halo", fill: false })
      .bindTooltip(h("span", {}, districtName(outline.kind, outline.number)), { sticky: true })
      .on("click", () => pickDistrict(outline.kind));
    const line = L.polygon(rings, { className: `map-outline ${outline.kind}`, fill: false, interactive: false });
    halo.addTo(map);
    line.addTo(map);
    return [outline.kind, { halo, line }];
  }));
  placePin();
  styleLines();
  fitView();

  const notUp = new Set(ballot.districts.not_up || []);
  const mapLabel = ballot.districts.election_precinct?.map_label;
  parts.picks.replaceChildren(...data.outlines.map((outline) => {
    const name = districtName(outline.kind, outline.number);
    const title = notUp.has(outline.kind) ? `${name}: not up for election this time`
      : outline.kind === "election_precinct" && mapLabel ? `Election precinct ${outline.number}, from the map “${mapLabel}”`
        : name;
    return h("button", {
      type: "button", class: ["map-pick", outline.kind, notUp.has(outline.kind) && "not-up"],
      "data-map-kind": outline.kind, "aria-pressed": String(outline.kind === highlight), title,
      on: { click: () => pickDistrict(outline.kind) },
    }, swatch(outline.kind), kindLabel(outline.kind, "short"), " ", h("strong", {}, numberText(outline.kind, outline.number)));
  }));
  const fromCouncil = (outline) => outline.kind === "sboe" || outline.kind === "election_precinct";
  const sources = [
    data.outlines.some((outline) => !fromCouncil(outline)) && "the US Census (TIGERweb)",
    data.outlines.some(fromCouncil) && "the Texas Legislative Council",
  ].filter(Boolean).join(" and ");
  const precise = data.outlines.some((outline) => outline.kind === "election_precinct") ? " (your precinct to about 16 feet)" : "";
  const notes = data.street_map ? data.notes : [...data.notes, "The street map is turned off in Settings."];
  parts.notes.replaceChildren(...notes.map((note) => h("p", { class: "district-note" }, note)));
  parts.foot.replaceChildren(
    sources ? `Outlines from ${sources}, simplified to about 160 feet${precise}: near a boundary, go by the district numbers. ` : "",
    data.street_map ? "The street map comes from OpenStreetMap, through Pallot." : "");
}

function makeMap(region) {
  if (map) return;
  map = L.map(parts.canvas, {
    minZoom: 5, maxZoom: 18, maxBounds: region, zoomSnap: 0.5,
    scrollWheelZoom: false, dragging: !touch, zoomAnimation: !still, fadeAnimation: !still,
  });
  map.setView([ballot.location.lat, ballot.location.lon], 12); // Leaflet needs a view before any layer
  map.attributionControl.setPrefix(LEAFLET_CREDIT);
  L.control.scale({ imperial: true, metric: false }).addTo(map);
  const Home = L.Control.extend({
    options: { position: "topleft" },
    onAdd() {
      const button = h("a", {
        href: "#", role: "button", class: "map-home", title: "Back to your address", "aria-label": "Back to your address",
      }, icon("pin"));
      L.DomEvent.on(button, "click", (event) => {
        L.DomEvent.preventDefault(event);
        if (highlight) pickDistrict(highlight);
        else fitView();
      });
      const bar = h("div", { class: "leaflet-bar" }, button);
      L.DomEvent.disableClickPropagation(bar);
      return bar;
    },
  });
  new Home().addTo(map);
  map.on("focus", () => map.scrollWheelZoom.enable());
  map.on("blur", () => map.scrollWheelZoom.disable());
}

function placePin() {
  if (!map) return;
  const { lat, lon, approximate, source } = ballot.location;
  if (pin) {
    pin.setLatLng([lat, lon]);
  } else {
    pin = L.circleMarker([lat, lon], { radius: 7, className: "map-pin" }).addTo(map);
  }
  pin.unbindTooltip().bindTooltip(h("span", {}, source === "voter_card" ? "A point in your precinct"
    : approximate ? "Your address (approximate)" : "Your address"));
  pin.bringToFront();
}

function styleLines() {
  for (const [kind, { halo, line }] of lines) {
    line.getElement()?.classList.toggle("is-highlighted", kind === highlight);
    line.getElement()?.classList.toggle("is-faded", Boolean(highlight) && kind !== highlight);
    halo.getElement()?.classList.toggle("is-faded", Boolean(highlight) && kind !== highlight);
  }
  const picked = lines.get(highlight);
  if (picked) {
    picked.halo.bringToFront();
    picked.line.bringToFront();
  }
  pin?.bringToFront();
}

// A picked district fills the map. Otherwise the map centres on the address, zoomed so the
// smallest district fits around it, within HOME_ZOOM.
function fitView() {
  if (!map) return;
  const at = pin.getLatLng();
  const picked = lines.get(highlight);
  if (picked) {
    map.fitBounds(picked.line.getBounds().extend(at), { padding: [16, 16], maxZoom: 15, animate: !still });
    return;
  }
  const area = (b) => (b.getNorth() - b.getSouth()) * (b.getEast() - b.getWest());
  const [nearest] = [...lines.values()].map(({ line }) => line.getBounds()).sort((a, b) => area(a) - area(b));
  let zoom = 12;
  if (nearest) {
    const dLat = Math.max(nearest.getNorth() - at.lat, at.lat - nearest.getSouth());
    const dLng = Math.max(nearest.getEast() - at.lng, at.lng - nearest.getWest());
    const around = L.latLngBounds([at.lat - dLat, at.lng - dLng], [at.lat + dLat, at.lng + dLng]);
    zoom = map.getBoundsZoom(around, false, L.point(32, 32));
  }
  map.setView(at, Math.min(HOME_ZOOM[1], Math.max(HOME_ZOOM[0], zoom)), { animate: !still });
}
