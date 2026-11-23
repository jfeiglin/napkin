// The map: one marker for each place, all alike; markers that would touch move apart and keep a stem back to
// their place. The attack line bows from the attack to the chosen place.

import { FRAME } from './geo';
import { px, r1 } from './format';
import type { Point } from './types';

export const MX = 116;
export const MW = 704;

interface Marker {
  p: Point;
  ax: number;
  ay: number;
  x: number;
  y: number;
  r: number;
}

// Markers that would touch move apart, each by half of the overlap, until none touch.
export function spread(points: Point[], s: number, my: number, radius = 7): Marker[] {
  const pts = points.map((p) => {
    const x = MX + p.x * s;
    const y = my + p.y * s;
    return { p, ax: x, ay: y, x, y, r: radius };
  });
  for (let it = 0; it < 120; it++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i];
        const b = pts[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dd = Math.hypot(dx, dy) || 0.01;
        const want = a.r + b.r + 3;
        if (dd < want) {
          const push = (want - dd) / 2 + 0.2;
          const ux = dx / dd;
          const uy = dy / dd;
          a.x -= ux * push;
          a.y -= uy * push;
          b.x += ux * push;
          b.y += uy * push;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  return pts;
}

export function mapLayout(points: Point[], chosen: string) {
  const s = MW / FRAME[0];
  const MH = FRAME[1] * s;
  const MY = 176 + Math.round((540 - MH) / 2);
  const pts = spread(points, s, MY);
  const stems: string[] = [];
  const anchors: string[] = [];
  const dots: { key: string; css: string; aria: string }[] = [];
  const dotLabels: { text: string; css: string }[] = [];
  pts.forEach((q) => {
    const p = q.p;
    const on = p.key === chosen;
    if (Math.hypot(q.x - q.ax, q.y - q.ay) > 1) {
      stems.push('M ' + r1(q.ax) + ' ' + r1(q.ay) + ' L ' + r1(q.x) + ' ' + r1(q.y));
      anchors.push('M ' + r1(q.ax - 1.8) + ' ' + r1(q.ay) + ' a1.8 1.8 0 1 0 3.6 0 a1.8 1.8 0 1 0 -3.6 0');
    }
    let css = 'left: ' + px(q.x - q.r) + '; top: ' + px(q.y - q.r) + '; width: ' + px(2 * q.r) + '; height: ' + px(2 * q.r) + ';';
    css += ' background: #2A78D6;' + (on ? ' box-shadow: 0 0 0 3px #FFFFFF, 0 0 0 5px #16181D;' : ' box-shadow: 0 0 0 1.5px #FFFFFF;');
    const n = p.systems;
    dots.push({ key: p.key, css, aria: p.name + ': ' + n + (n === 1 ? ' water system' : ' water systems') });
    if (on) {
      const w = 12 + p.name.length * 6.6;
      let lx = q.x + q.r + 6;
      const ly = q.y - 8;
      let align = 'left';
      if (lx + w > MX + MW) {
        lx = q.x - q.r - 6 - w;
        align = 'right';
      }
      dotLabels.push({
        text: p.name,
        css: 'left: ' + px(lx) + '; top: ' + px(ly) + '; width: ' + px(w) + '; text-align: ' + align + '; text-shadow: 0 0 3px #FFFFFF, 0 0 3px #FFFFFF;',
      });
    }
  });
  const HX0 = 72;
  const HY0 = 222;
  const HR = 24;
  let atkLine = '';
  let atkHead = '';
  const target = pts.find((q) => q.p.key === chosen);
  if (target) {
    const vx = target.x - HX0;
    const vy = target.y - HY0;
    const dist = Math.hypot(vx, vy) || 1;
    let nx = vy / dist;
    let ny = -vx / dist;
    if (ny > 0) {
      nx = -nx;
      ny = -ny;
    }
    const bow = Math.min(90, 0.22 * dist);
    const cx = (HX0 + target.x) / 2 + nx * bow;
    const cy = (HY0 + target.y) / 2 + ny * bow;
    const sx0 = cx - HX0;
    const sy0 = cy - HY0;
    const sl = Math.hypot(sx0, sy0) || 1;
    const x0 = HX0 + (sx0 / sl) * (HR + 5);
    const y0 = HY0 + (sy0 / sl) * (HR + 5);
    let ux2 = target.x - cx;
    let uy2 = target.y - cy;
    const ul = Math.hypot(ux2, uy2) || 1;
    ux2 /= ul;
    uy2 /= ul;
    const ex = target.x - ux2 * (target.r + 7);
    const ey = target.y - uy2 * (target.r + 7);
    atkLine = 'M ' + r1(x0) + ' ' + r1(y0) + ' Q ' + r1(cx) + ' ' + r1(cy) + ' ' + r1(ex - ux2 * 5) + ' ' + r1(ey - uy2 * 5);
    atkHead =
      'M ' + r1(ex) + ' ' + r1(ey) + ' L ' + r1(ex - ux2 * 8 - uy2 * 4.5) + ' ' + r1(ey - uy2 * 8 + ux2 * 4.5) +
      ' L ' + r1(ex - ux2 * 8 + uy2 * 4.5) + ' ' + r1(ey - uy2 * 8 - ux2 * 4.5) + ' Z';
  }
  return {
    mapBox: '0 0 ' + FRAME[0] + ' ' + FRAME[1],
    mapCss: 'left: ' + px(MX) + '; top: ' + px(MY) + '; width: ' + px(MW) + '; height: ' + px(MH) + ';',
    hintCss: 'left: ' + px(MX) + '; top: ' + px(MY + MH + 10) + '; width: ' + px(MW) + ';',
    stemPath: stems.join(' '),
    anchorPath: anchors.join(' '),
    dots,
    dotLabels,
    atkLine,
    atkHead,
  };
}
