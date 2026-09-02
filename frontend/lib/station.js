/* The station canvas, used identically on the home page and in the game.
 *
 * render.js is loaded as a classic script in index.html and exposes StationView
 * globally. It is the same renderer the dev preview and the printed sector
 * handbook use, so all four views of the map are drawn by one implementation. */

let cached = null;

export async function stationData() {
  if (!cached) {
    const res = await fetch('/api/station');
    cached = await res.json();
  }
  return cached;
}

/* Mount a station canvas into `host`. `onDoorClick` receives the door id.
 * Pass onDoorClick = null for a read-only map. */
export function mountStation(host, station, onDoorClick) {
  host.innerHTML = '';
  const box = document.createElement('div');
  box.className = 'stationbox';
  const canvas = document.createElement('canvas');
  box.appendChild(canvas);
  host.appendChild(box);

  const Ctor = window.StationView;
  if (typeof Ctor !== 'function') {
    throw new Error('station/render.js did not load — the map cannot be drawn');
  }
  const view = new Ctor(canvas, station, {
    onDoorClick: onDoorClick ? id => onDoorClick(id) : null,
    interactive: Boolean(onDoorClick),
  });
  // resize() measures the parent, which has no width until it is in the DOM.
  requestAnimationFrame(() => view.resize());
  return view;
}

export function legend(s) {
  const el = document.createElement('div');
  el.className = 'legend';
  el.innerHTML = `
    <span><i style="background:#00ff40"></i>${s.legendOpen}</span>
    <span><i style="background:#ff1a1a"></i>${s.legendClosed}</span>
    <span><i style="background:#7d8589"></i>${s.legendPermanent}</span>
    <span>${s.legendClick}</span>`;
  return el;
}
