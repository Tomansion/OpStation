/*
 * OpStation — station map renderer.
 *
 * Framework-free. Draws station.json onto a 2D canvas and hit-tests door clicks.
 * The Angular component wraps this; station/preview.html uses it directly.
 *
 *   const view = new StationView(canvas, station, { onDoorClick: id => {...} });
 *   view.setDoorState('D5', 'closed');
 *   view.setDoorStates({ D1: 'open', H3: 'closed' });
 */

const THEME = {
  bg:            '#0b0d0e',
  space:         '#07080a',
  spaceHatch:    '#141819',
  corridorFill:  '#171c1e',
  corridorEdge:  '#39454a',
  roomFill:      '#13171a',
  roomEdge:      '#2f3a3e',
  hangarFill:    '#15191c',
  hangarEdge:    '#3c4a50',
  label:         '#8fa0a6',
  labelDim:      '#5c6a70',
  doorOpen:      '#2fbf6b',
  doorClosed:    '#d0413f',
  doorEdge:      '#0b0d0e',
  doorLabel:     '#c8d3d6',
  passage:       '#2a3235',
  hover:         '#f0c040',
  font:          "11px 'JetBrains Mono', 'IBM Plex Mono', 'DejaVu Sans Mono', monospace",
  fontSmall:     "9px 'JetBrains Mono', 'IBM Plex Mono', 'DejaVu Sans Mono', monospace",
  fontDoor:      "bold 10px 'JetBrains Mono', 'IBM Plex Mono', 'DejaVu Sans Mono', monospace",
};

const DOOR_THICKNESS = 9;   // px, at scale 1
const HIT_INFLATE    = 8;   // px, clickable margin around a door bar

class StationView {
  constructor(canvas, station, opts = {}) {
    this.canvas  = canvas;
    this.station = station;
    this.onDoorClick = opts.onDoorClick || null;
    this.interactive = opts.interactive !== false;
    this.showLabels  = opts.showLabels !== false;

    this.doorStates = {};
    for (const d of station.doors) this.doorStates[d.id] = d.initial;

    this.hoverId = null;
    this.scale = 1;
    this.offX = 0;
    this.offY = 0;

    this._bind();
    this.resize();
  }

  /* ---- public API ---- */

  setDoorState(id, state) {
    if (!(id in this.doorStates)) throw new Error('unknown door ' + id);
    this.doorStates[id] = state;
    this.draw();
  }

  setDoorStates(map) {
    for (const [id, state] of Object.entries(map)) {
      if (id in this.doorStates) this.doorStates[id] = state;
    }
    this.draw();
  }

  getDoorState(id) { return this.doorStates[id]; }

  resize() {
    const g = this.station.grid;
    const dpr = window.devicePixelRatio || 1;
    const box = this.canvas.parentElement || this.canvas;
    const availW = box.clientWidth  || g.cols * g.cell;
    const availH = box.clientHeight || g.rows * g.cell;

    this.scale = Math.min(availW / (g.cols * g.cell), availH / (g.rows * g.cell));
    const w = g.cols * g.cell * this.scale;
    const h = g.rows * g.cell * this.scale;

    this.canvas.style.width  = w + 'px';
    this.canvas.style.height = h + 'px';
    this.canvas.width  = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.dpr = dpr;
    this.draw();
  }

  /* ---- geometry ---- */

  // grid units -> device px
  gx(v) { return v * this.station.grid.cell * this.scale * this.dpr; }

  barRect(bar) {
    const t = DOOR_THICKNESS * this.scale * this.dpr;
    const x = this.gx(bar.x), y = this.gx(bar.y), L = this.gx(bar.len);
    return bar.orient === 'h'
      ? { x: x,         y: y - t / 2, w: L, h: t }
      : { x: x - t / 2, y: y,         w: t, h: L };
  }

  doorAt(px, py) {
    const pad = HIT_INFLATE * this.scale * this.dpr;
    for (const d of this.station.doors) {
      const r = this.barRect(d.bar);
      if (px >= r.x - pad && px <= r.x + r.w + pad &&
          py >= r.y - pad && py <= r.y + r.h + pad) return d;
    }
    return null;
  }

  /* ---- drawing ---- */

  draw() {
    const ctx = this.canvas.getContext('2d');
    const g = this.station.grid;

    ctx.fillStyle = THEME.bg;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    this._drawSpaceMargins(ctx, g);
    for (const a of this.station.areas) this._drawArea(ctx, a);
    for (const p of this.station.passages) this._drawPassage(ctx, p);
    for (const d of this.station.doors) this._drawDoor(ctx, d);
    if (this.showLabels) this._drawExteriorLabels(ctx);
  }

  _drawSpaceMargins(ctx, g) {
    ctx.fillStyle = THEME.space;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    // diagonal hatch over the whole field; the station boxes paint over it
    ctx.strokeStyle = THEME.spaceHatch;
    ctx.lineWidth = 1 * this.dpr;
    const step = 14 * this.scale * this.dpr;
    ctx.beginPath();
    for (let x = -this.canvas.height; x < this.canvas.width; x += step) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x + this.canvas.height, this.canvas.height);
    }
    ctx.stroke();
  }

  _areaStyle(kind) {
    if (kind === 'corridor')   return [THEME.corridorFill, THEME.corridorEdge];
    if (kind === 'hangar_bay') return [THEME.hangarFill,   THEME.hangarEdge];
    return [THEME.roomFill, THEME.roomEdge];
  }

  _drawArea(ctx, area) {
    const [fill, edge] = this._areaStyle(area.kind);
    ctx.lineWidth = 1.5 * this.scale * this.dpr;

    for (const [x, y, w, h] of area.rects) {
      const rx = this.gx(x), ry = this.gx(y), rw = this.gx(w), rh = this.gx(h);
      ctx.fillStyle = fill;
      ctx.fillRect(rx, ry, rw, rh);
      ctx.strokeStyle = edge;
      ctx.strokeRect(rx, ry, rw, rh);
    }

    if (!this.showLabels) return;

    // label the largest rect
    const big = area.rects.reduce((a, b) => (a[2] * a[3] >= b[2] * b[3] ? a : b));
    const cx = this.gx(big[0] + big[2] / 2);
    const cy = this.gx(big[1] + big[3] / 2);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const s = this.scale * this.dpr;
    ctx.font = THEME.font.replace('11px', `${Math.max(8, 11 * s)}px`);
    ctx.fillStyle = area.kind === 'corridor' ? THEME.labelDim : THEME.label;

    if (area.sub) {
      ctx.fillText(area.name, cx, cy - 7 * s);
      ctx.font = THEME.fontSmall.replace('9px', `${Math.max(7, 9 * s)}px`);
      ctx.fillStyle = THEME.labelDim;
      ctx.fillText(area.sub, cx, cy + 7 * s);
    } else {
      ctx.fillText(area.name, cx, cy);
    }
  }

  _drawPassage(ctx, p) {
    const r = this.barRect(p.bar);
    ctx.fillStyle = THEME.passage;
    ctx.fillRect(r.x, r.y, r.w, r.h);
  }

  _drawDoor(ctx, d) {
    const r = this.barRect(d.bar);
    const open = this.doorStates[d.id] === 'open';

    if (open) {
      // an open door reads as a gap: thin outline, hollow centre
      ctx.strokeStyle = THEME.doorOpen;
      ctx.lineWidth = 2 * this.scale * this.dpr;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.fillStyle = THEME.bg;
      ctx.fillRect(r.x + r.w * 0.18, r.y + r.h * 0.18, r.w * 0.64, r.h * 0.64);
    } else {
      ctx.fillStyle = THEME.doorClosed;
      ctx.fillRect(r.x, r.y, r.w, r.h);
      ctx.strokeStyle = THEME.doorEdge;
      ctx.lineWidth = 1 * this.dpr;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
    }

    if (this.hoverId === d.id) {
      const pad = HIT_INFLATE * this.scale * this.dpr;
      ctx.strokeStyle = THEME.hover;
      ctx.lineWidth = 1.5 * this.dpr;
      ctx.strokeRect(r.x - pad, r.y - pad, r.w + pad * 2, r.h + pad * 2);
    }

    if (!this.showLabels) return;

    const s = this.scale * this.dpr;
    ctx.font = THEME.fontDoor.replace('10px', `${Math.max(8, 10 * s)}px`);
    ctx.fillStyle = THEME.doorLabel;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    const off = 15 * s;
    if (d.bar.orient === 'h') {
      // hangar doors label outward, internal doors label to the side
      const above = d.outward === 'up' || (!d.outward && d.bar.x < 6);
      ctx.fillText(d.id, r.x + r.w / 2, above ? r.y - off : r.y + r.h + off);
    } else {
      ctx.fillText(d.id, d.outward === 'right' ? r.x + r.w + off * 1.4 : r.x - off * 1.4, r.y + r.h / 2);
    }
  }

  _drawExteriorLabels(ctx) {
    const s = this.scale * this.dpr;
    ctx.font = THEME.fontSmall.replace('9px', `${Math.max(7, 9 * s)}px`);
    ctx.fillStyle = THEME.labelDim;
    ctx.textBaseline = 'middle';
    for (const l of this.station.exterior_labels || []) {
      ctx.save();
      ctx.translate(this.gx(l.x), this.gx(l.y));
      if (l.rotate) ctx.rotate(l.rotate * Math.PI / 180);
      ctx.textAlign = l.align || 'center';
      ctx.fillText(l.text, 0, 0);
      ctx.restore();
    }
  }

  /* ---- input ---- */

  _bind() {
    if (!this.interactive) return;
    const local = ev => {
      const b = this.canvas.getBoundingClientRect();
      return [(ev.clientX - b.left) * this.dpr, (ev.clientY - b.top) * this.dpr];
    };

    this.canvas.addEventListener('mousemove', ev => {
      const [x, y] = local(ev);
      const d = this.doorAt(x, y);
      const id = d ? d.id : null;
      if (id !== this.hoverId) {
        this.hoverId = id;
        this.canvas.style.cursor = id ? 'pointer' : 'default';
        this.canvas.title = id ? `${id} — ${this.doorStates[id]}` : '';
        this.draw();
      }
    });

    this.canvas.addEventListener('mouseleave', () => {
      if (this.hoverId) { this.hoverId = null; this.draw(); }
    });

    this.canvas.addEventListener('click', ev => {
      const [x, y] = local(ev);
      const d = this.doorAt(x, y);
      if (d && this.onDoorClick) this.onDoorClick(d.id, this.doorStates[d.id]);
    });

    window.addEventListener('resize', () => this.resize());
  }
}

if (typeof module !== 'undefined') module.exports = { StationView, THEME };
