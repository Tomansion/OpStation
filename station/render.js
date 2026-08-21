/*
 * OpStation — station map renderer.
 *
 * Framework-free. Draws station.json onto a 2D canvas and hit-tests door clicks.
 * The Angular component wraps this; station/preview.html uses it directly.
 *
 *   const view = new StationView(canvas, station, { onDoorClick: id => {...} });
 *   view.setDoorState('D5', 'closed');
 *   view.setDoorStates({ D1: 'open', H3: 'closed' });
 *
 * Drawing model, in order:
 *   1. hatched space over the whole field
 *   2. every area filled flat, no outline — so a multi-rect area (the T-shaped
 *      corridors) reads as one shape, and there are no borders to look tidy
 *   3. a dark seam on every edge shared by two DIFFERENT areas — this is the only
 *      line work on the map, and it is what separates Living Quarters from the
 *      Observation Deck
 *   4. doorless passages: the seam is broken and jamb ticks are drawn, so an
 *      opening looks like an opening
 *   5. door bars, hot green or hot red, on top of the seam
 */

const THEME = {
  space:        '#000000',
  spaceHatch:   '#131313',
  corridor:     '#4a4f52',
  room:         '#2e3234',
  hangarBay:    '#3b4043',
  seam:         '#0a0a0a',
  jamb:         '#b8c0c4',
  threshold:    '#7d8589',

  doorOpen:     '#00ff40',
  doorClosed:   '#ff1a1a',
  hover:        '#ffff00',
  sealed:       'rgba(255, 176, 0, 0.20)',
  sealedEdge:   '#ffb000',

  areaLabel:    '#e8ecec',
  areaSub:      '#9aa3a5',
  corridorLbl:  '#00e5ff',
  doorLabel:    '#ffffff',
  exterior:     '#4d5457',

  font:         'Courier New, Courier, monospace',
};

const DOOR_THICKNESS = 11;  // px at scale 1
const SEAM_WIDTH     = 3;
const HIT_INFLATE    = 8;
const EPS            = 1e-6;

class StationView {
  constructor(canvas, station, opts = {}) {
    this.canvas = canvas;
    this.station = station;
    this.onDoorClick = opts.onDoorClick || null;
    this.interactive = opts.interactive !== false;
    this.showLabels = opts.showLabels !== false;
    // compact: drop secondary and exterior labels and shorten corridor names,
    // for small print cards. subLabels alone drops just the second line.
    this.compact = opts.compact === true;
    this.subLabels = opts.subLabels !== false && !this.compact;

    this.doorStates = {};
    for (const d of station.doors) this.doorStates[d.id] = d.initial;

    this.fill = {};
    for (const a of station.areas) {
      this.fill[a.id] = a.kind === 'corridor' ? THEME.corridor
                      : a.kind === 'hangar_bay' ? THEME.hangarBay
                      : THEME.room;
    }

    this.seams = this._computeSeams();
    this.highlight = [];   // area ids drawn as a sealed volume
    this.hoverId = null;
    this._bind();
    this.resize();
  }

  /* ---------------- public API ---------------- */

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

  /* Tint a set of areas as a sealed volume. Pass [] to clear. */
  setHighlight(areaIds) {
    this.highlight = areaIds || [];
    this.draw();
  }

  resize() {
    const g = this.station.grid;
    const dpr = window.devicePixelRatio || 1;
    const box = this.canvas.parentElement || this.canvas;
    const availW = box.clientWidth || g.cols * g.cell;
    const availH = box.clientHeight || g.rows * g.cell;

    this.scale = Math.min(availW / (g.cols * g.cell), availH / (g.rows * g.cell));
    this.dpr = dpr;

    const w = g.cols * g.cell * this.scale;
    const h = g.rows * g.cell * this.scale;
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.draw();
  }

  /* ---------------- geometry ---------------- */

  gx(v) { return v * this.station.grid.cell * this.scale * this.dpr; }

  barRect(bar) {
    const t = DOOR_THICKNESS * this.scale * this.dpr;
    const x = this.gx(bar.x), y = this.gx(bar.y), L = this.gx(bar.len);
    return bar.orient === 'h'
      ? { x, y: y - t / 2, w: L, h: t }
      : { x: x - t / 2, y, w: t, h: L };
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

  /*
   * Every edge segment shared by two DIFFERENT areas. Rects of the same area
   * are skipped, which is what lets a T-shaped corridor read as one shape.
   */
  _computeSeams() {
    const out = [];
    const areas = this.station.areas;

    for (let i = 0; i < areas.length; i++) {
      for (let j = i + 1; j < areas.length; j++) {
        for (const [ax, ay, aw, ah] of areas[i].rects) {
          for (const [bx, by, bw, bh] of areas[j].rects) {
            // vertical touch: a's bottom on b's top, or vice versa
            for (const [ya, yb] of [[ay + ah, by], [by + bh, ay]]) {
              if (Math.abs(ya - yb) < EPS) {
                const x0 = Math.max(ax, bx), x1 = Math.min(ax + aw, bx + bw);
                if (x1 - x0 > EPS) out.push({ orient: 'h', y: ya, x0, x1 });
              }
            }
            // horizontal touch: a's right on b's left, or vice versa
            for (const [xa, xb] of [[ax + aw, bx], [bx + bw, ax]]) {
              if (Math.abs(xa - xb) < EPS) {
                const y0 = Math.max(ay, by), y1 = Math.min(ay + ah, by + bh);
                if (y1 - y0 > EPS) out.push({ orient: 'v', x: xa, y0, y1 });
              }
            }
          }
        }
      }
    }
    return out;
  }

  /* ---------------- drawing ---------------- */

  draw() {
    const ctx = this.canvas.getContext('2d');
    this._drawSpace(ctx);
    for (const a of this.station.areas) this._fillArea(ctx, a);
    this._drawSeams(ctx);
    this._drawHighlight(ctx);
    for (const p of this.station.passages) this._drawPassage(ctx, p);
    for (const d of this.station.doors) this._drawDoor(ctx, d);
    if (this.showLabels) {
      for (const a of this.station.areas) this._labelArea(ctx, a);
      for (const d of this.station.doors) this._labelDoor(ctx, d);
      this._drawExteriorLabels(ctx);
    }
  }

  _drawSpace(ctx) {
    ctx.fillStyle = THEME.space;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.strokeStyle = THEME.spaceHatch;
    ctx.lineWidth = 1 * this.dpr;
    const step = 12 * this.scale * this.dpr;
    ctx.beginPath();
    for (let x = -this.canvas.height; x < this.canvas.width; x += step) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x + this.canvas.height, this.canvas.height);
    }
    ctx.stroke();
  }

  _fillArea(ctx, area) {
    ctx.fillStyle = this.fill[area.id];
    for (const [x, y, w, h] of area.rects) {
      ctx.fillRect(this.gx(x), this.gx(y), this.gx(w), this.gx(h));
    }
  }

  /*
   * A sealed volume: tint every rect of every area inside it. Drawn under the
   * doors so the cut-set stays the most prominent thing on screen.
   */
  _drawHighlight(ctx) {
    if (!this.highlight.length) return;
    const set = new Set(this.highlight);
    ctx.fillStyle = THEME.sealed;
    for (const a of this.station.areas) {
      if (!set.has(a.id)) continue;
      for (const [x, y, w, h] of a.rects) {
        ctx.fillRect(this.gx(x), this.gx(y), this.gx(w), this.gx(h));
      }
    }
  }

  _drawSeams(ctx) {
    ctx.strokeStyle = THEME.seam;
    ctx.lineWidth = SEAM_WIDTH * this.scale * this.dpr;
    ctx.beginPath();
    for (const s of this.seams) {
      if (s.orient === 'h') {
        ctx.moveTo(this.gx(s.x0), this.gx(s.y));
        ctx.lineTo(this.gx(s.x1), this.gx(s.y));
      } else {
        ctx.moveTo(this.gx(s.x), this.gx(s.y0));
        ctx.lineTo(this.gx(s.x), this.gx(s.y1));
      }
    }
    ctx.stroke();
  }

  /*
   * A doorless passage: break the seam over the opening, then mark the two
   * jambs. Reads as a gap in the wall rather than as an unexplained bar.
   */
  _drawPassage(ctx, p) {
    const b = p.bar;
    const s = this.scale * this.dpr;
    const jamb = 9 * s;

    const a0 = this.gx(b.x), b0 = this.gx(b.y);
    const a1 = b.orient === 'h' ? this.gx(b.x + b.len) : a0;
    const b1 = b.orient === 'h' ? b0 : this.gx(b.y + b.len);

    // 1. erase the seam over the opening
    ctx.strokeStyle = this.fill[p.between[0]];
    ctx.lineWidth = (SEAM_WIDTH + 2) * s;
    ctx.beginPath();
    ctx.moveTo(a0, b0);
    ctx.lineTo(a1, b1);
    ctx.stroke();

    // 2. pale threshold band across it — this is what makes it read as walkable
    ctx.strokeStyle = THEME.threshold;
    ctx.lineWidth = 2 * s;
    ctx.setLineDash([3 * s, 3 * s]);
    ctx.beginPath();
    ctx.moveTo(a0, b0);
    ctx.lineTo(a1, b1);
    ctx.stroke();
    ctx.setLineDash([]);

    // 3. jamb ticks at both ends, perpendicular to the wall
    ctx.strokeStyle = THEME.jamb;
    ctx.lineWidth = 3 * s;
    ctx.beginPath();
    if (b.orient === 'h') {
      for (const gx of [a0, a1]) {
        ctx.moveTo(gx, b0 - jamb);
        ctx.lineTo(gx, b0 + jamb);
      }
    } else {
      for (const gy of [b0, b1]) {
        ctx.moveTo(a0 - jamb, gy);
        ctx.lineTo(a0 + jamb, gy);
      }
    }
    ctx.stroke();
  }

  _drawDoor(ctx, d) {
    const r = this.barRect(d.bar);
    const open = this.doorStates[d.id] === 'open';
    ctx.fillStyle = open ? THEME.doorOpen : THEME.doorClosed;
    ctx.fillRect(r.x, r.y, r.w, r.h);

    if (open) {
      // an open door reads as a gap: punch the middle out
      ctx.fillStyle = THEME.space;
      const inset = 3 * this.scale * this.dpr;
      if (d.bar.orient === 'h') ctx.fillRect(r.x + inset, r.y + inset, r.w - inset * 2, r.h - inset * 2);
      else                      ctx.fillRect(r.x + inset, r.y + inset, r.w - inset * 2, r.h - inset * 2);
    }

    if (this.hoverId === d.id) {
      const pad = HIT_INFLATE * this.scale * this.dpr;
      ctx.strokeStyle = THEME.hover;
      ctx.lineWidth = 2 * this.dpr;
      ctx.strokeRect(r.x - pad, r.y - pad, r.w + pad * 2, r.h + pad * 2);
    }
  }

  _font(px, bold) {
    const s = Math.max(8, px * this.scale * this.dpr);
    return `${bold ? 'bold ' : ''}${s}px ${THEME.font}`;
  }

  _labelArea(ctx, area) {
    const big = area.rects.reduce((a, b) => (a[2] * a[3] >= b[2] * b[3] ? a : b));
    const cx = this.gx(big[0] + big[2] / 2);
    const cy = this.gx(big[1] + big[3] / 2);
    const s = this.scale * this.dpr;

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    if (area.kind === 'corridor') {
      ctx.font = this._font(12, true);
      ctx.fillStyle = THEME.corridorLbl;
      // "C1  NORTH CORRIDOR" -> "C1" when there is no room for the full name
      ctx.fillText(this.compact ? area.name.split(/\s{2,}/)[0] : area.name, cx, cy);
      return;
    }

    ctx.font = this._font(12, true);
    ctx.fillStyle = THEME.areaLabel;
    if (area.sub && this.subLabels) {
      ctx.fillText(area.name, cx, cy - 8 * s);
      ctx.font = this._font(10, false);
      ctx.fillStyle = THEME.areaSub;
      ctx.fillText(area.sub, cx, cy + 8 * s);
    } else {
      ctx.fillText(area.name, cx, cy);
    }
  }

  _labelDoor(ctx, d) {
    const r = this.barRect(d.bar);
    const s = this.scale * this.dpr;
    const off = 13 * s;
    // optional per-door nudge in grid cells, for hand-tuning tight spots
    const nx = this.gx(d.label_nudge ? (d.label_nudge.x || 0) : 0);
    const ny = this.gx(d.label_nudge ? (d.label_nudge.y || 0) : 0);
    const cx = r.x + r.w / 2 + nx, cy = r.y + r.h / 2 + ny;

    ctx.font = this._font(12, true);
    ctx.fillStyle = THEME.doorLabel;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'center';

    switch (d.label) {
      case 'up':    ctx.fillText(d.id, cx, r.y - off + ny); break;
      case 'down':  ctx.fillText(d.id, cx, r.y + r.h + off + ny); break;
      case 'left':  ctx.textAlign = 'right'; ctx.fillText(d.id, r.x - off * 0.6 + nx, cy); break;
      case 'right': ctx.textAlign = 'left';  ctx.fillText(d.id, r.x + r.w + off * 0.6 + nx, cy); break;
      default:      ctx.fillText(d.id, cx, r.y - off + ny);
    }
  }

  _drawExteriorLabels(ctx) {
    if (this.compact) return;
    ctx.font = this._font(10, false);
    ctx.fillStyle = THEME.exterior;
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

  /* ---------------- input ---------------- */

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
        this.canvas.title = id ? `${id} ${this.doorStates[id].toUpperCase()}` : '';
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
