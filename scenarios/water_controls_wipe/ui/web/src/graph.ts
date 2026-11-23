// The place's water systems at the time on the slider. Each system is a row: the attack comes in
// from the left; its bars show what its plants can make, what it buys and its stored water; the arrow on its
// right is the water it delivers to its homes against their normal use; its hospitals are under its homes.
// A system that sells to another is above it, and each sale is a line in the lane on the left of the rows.

import { amount, count, px, r1, sample, when } from './format';
import type { Frame, Place, System, Tie } from './types';

export const GH = 540;
export const UX = 210;
const UW = 360;
const HX = 652;
const HW = 128;
const PAD = 10;
const BH = 15;
const BP = 19;
const TOP = 27;
const GAP = 14;
const AGX = 66;
const AGY = 46;
const BLUE = '#2A78D6';
const ORANGE = '#C2610C';
const RED = '#E34948';
const GREY = '#8A9099';
const ICONS = {
  drop: 'M12 3.5c-3.2 4.2-6 7.4-6 10.6a6 6 0 0 0 12 0c0-3.2-2.8-6.4-6-10.6z M9.2 14.6a2.9 2.9 0 0 0 2.6 2.6',
  tap: 'M3 7.5h8.5a3.5 3.5 0 0 1 3.5 3.5v2 M3 5.5v4 M13 13h4 M15 16.2c-.9 1.1-1.6 1.9-1.6 2.6a1.6 1.6 0 0 0 3.2 0c0-.7-.7-1.5-1.6-2.6z M7 5.5V3.5 M5.2 3.5h3.6',
  home: 'M3.5 11.2 12 4l8.5 7.2 M5.8 9.4V20h12.4V9.4 M10 20v-5.6h4V20',
};
const MODES: Record<string, { text: string; bg: string; tip: string }> = {
  disrupted: { text: 'Controls wiped', bg: RED, tip: 'Its controls are wiped, and operators do not run its plants by hand yet.' },
  manual: { text: 'Run by hand', bg: ORANGE, tip: 'Operators run its plants by hand.' },
  recovered: { text: 'Controls restored', bg: BLUE, tip: 'Its controls are restored.' },
};
export const HCOLORS: Record<string, string> = { ok: BLUE, degraded: ORANGE, failed: RED };

type Key = 'prod' | 'imp' | 'stored' | 'del' | 'adv' | 'ctl' | 'mode';

interface Row {
  sys: System;
  bars: { kind: 'make' | 'buy' | 'stored'; v: number; full: number }[];
  H: number;
  HL: number;
  reached: boolean;
  nIn: number;
  nOut: number;
  y: number;
  accessY: number;
}

export interface Lane {
  t: Tie;
  seller: number;
  buyer: number;
  ia: number;
  ib: number;
  x: number;
}

// The lanes of the sales, from the innermost out: by the buyer's row, then the nearest seller first. Each one
// leaves its seller low on the left side and comes into its buyer high on the left side, so they do not cross.
// `order` is the systems in their rows, top down.
export function lanes(order: string[], ties: Tie[]): { lanes: Lane[]; nIn: number[]; nOut: number[] } {
  const idx = (id: string) => order.indexOf(id);
  const nIn = order.map(() => 0);
  const nOut = order.map(() => 0);
  const sorted = ties.slice().sort((a, b) => idx(a.buyer) - idx(b.buyer) || idx(b.seller) - idx(a.seller));
  return {
    lanes: sorted.map((t, k) => {
      const a = idx(t.seller);
      const b = idx(t.buyer);
      return { t, seller: a, buyer: b, ia: nOut[a]++, ib: nIn[b]++, x: UX - 52 - 10 * k };
    }),
    nIn,
    nOut,
  };
}

export function graph(place: Place, res: Frame, now: number | null) {
  const value = (sys: System, k: Key) =>
    now === null ? res.before.flows[sys.id][k] : sample<number | string>(res.flows[sys.id][k] as never, now, k === 'stored');
  const num = (sys: System, k: Key) => Number(value(sys, k));
  const systems = place.systems.map((s) => ({ ...s, ...res.fixed[s.id] }));
  const rows: Row[] = systems.map((sys) => {
    const bars: Row['bars'] = [];
    if (sys.cap > 0) bars.push({ kind: 'make', v: num(sys, 'prod'), full: sys.cap });
    if (sys.icap > 0) bars.push({ kind: 'buy', v: num(sys, 'imp'), full: sys.icap });
    bars.push({ kind: 'stored', v: num(sys, 'stored'), full: sys.full });
    const reached = res.flows[sys.id].ctl.some((p) => p[1] === 'wiped');
    return { sys, bars, H: TOP + bars.length * BP + 4, HL: sys.hospitals.length ? 22 : 0, reached, nIn: 0, nOut: 0, y: 0, accessY: 0 };
  });
  const height = (gap: number) => rows.reduce((a, r) => a + r.H + r.HL, 0) + gap * (rows.length - 1);
  const gap = height(GAP) > GH && rows.length > 1 ? Math.max(4, GAP - (height(GAP) - GH) / (rows.length - 1)) : GAP;
  let y = Math.max(0, Math.round((GH - height(gap)) / 2));
  rows.forEach((r) => {
    r.y = y;
    y += r.H + r.HL + gap;
  });

  const found = lanes(
    rows.map((r) => r.sys.id),
    place.ties,
  );
  rows.forEach((r, i) => {
    r.nIn = found.nIn[i];
    r.nOut = found.nOut[i];
  });
  const entryY = (r: Row, i: number) => r.y + 12 + 16 * i;
  const exitY = (r: Row, i: number) => r.y + r.H - 10 - 8 * i;
  rows.forEach((r) => {
    const top = r.nIn ? 12 + 16 * (r.nIn - 1) : 0;
    const bottom = r.nOut ? r.H - 10 - 8 * (r.nOut - 1) : r.H;
    r.accessY = r.y + (top + bottom) / 2;
  });

  const AHH = 9;
  const AHL = 10;
  // An arrow-shaped gauge from x0 to x1 around y, 18 px high with a 10 px head, filled from the left to share.
  const gauge = (x0: number, x1: number, yy: number, share: number) => {
    const xf = x0 + share * (x1 - x0);
    const xh = x1 - AHL;
    const pts =
      xf <= xh
        ? [[x0, yy - AHH], [xf, yy - AHH], [xf, yy + AHH], [x0, yy + AHH]]
        : [
            [x0, yy - AHH],
            [xh, yy - AHH],
            [xf, yy - (AHH * (x1 - xf)) / AHL],
            [xf, yy + (AHH * (x1 - xf)) / AHL],
            [xh, yy + AHH],
            [x0, yy + AHH],
          ];
    return 'M ' + pts.map((q) => r1(q[0]) + ' ' + r1(q[1])).join(' L ') + ' Z';
  };
  const head = (x: number, yy: number) =>
    'M ' + r1(x - 6) + ' ' + r1(yy - 4) + ' L ' + r1(x - 6) + ' ' + r1(yy + 4) + ' L ' + r1(x) + ' ' + r1(yy) + ' Z';
  const curve = (x0: number, y0: number, x1: number, y1: number) => {
    const c = (x1 - x0) / 2;
    return 'M ' + r1(x0) + ' ' + r1(y0) + ' C ' + r1(x0 + c) + ' ' + r1(y0) + ' ' + r1(x1 - c) + ' ' + r1(y1) + ' ' + r1(x1) + ' ' + r1(y1);
  };

  // One bar: as long as its full amount against the largest of its kind (rates or stored water), filled to its
  // amount now; its name on it, or just after it when the bar is too short to hold it. An empty bar turns orange.
  const rateMax = Math.max(...rows.map((r) => Math.max(r.sys.cap, r.sys.icap)));
  const volMax = Math.max(...rows.map((r) => r.sys.full));
  const BWMAX = UW - 2 * PAD;
  const WORDS = { make: 'Can make', buy: 'Buys', stored: 'Stored' };
  const bar = (b: Row['bars'][number], i: number) => {
    const scale = b.kind === 'stored' ? volMax : rateMax;
    const caption = WORDS[b.kind];
    const share = b.full > 0 ? Math.max(0, Math.min(1, b.v / b.full)) : 0;
    const empty = b.v < 0.005;
    const w = Math.max(3, BWMAX * (scale > 0 ? b.full / scale : 0));
    const inside = w >= caption.length * 6.3 + 14;
    const tip =
      b.kind === 'make'
        ? 'Its plants can make ' + amount(b.v) + ' of ' + amount(b.full) + ' million gallons a day now.'
        : b.kind === 'buy'
          ? 'It buys ' + amount(b.v) + ' million gallons a day now, of the ' + amount(b.full) + ' it can buy.'
          : 'Its stored water: ' + amount(b.v) + ' of the ' + amount(b.full) + ' million gallons it can use.';
    return {
      caption,
      tip,
      fill: 'width: ' + r1(share * 100) + '%;',
      textCss: empty ? 'color: ' + ORANGE + ';' : 'color: #3A414B;',
      inCss: inside ? '' : 'display: none;',
      outCss: inside ? 'display: none;' : '',
      trackCss: 'background: ' + (empty ? '#FBE3D2' : '#E6EAEF') + ';',
      css: 'left: ' + px(PAD) + '; top: ' + px(TOP + i * BP) + '; width: ' + px(w) + ';',
    };
  };

  const util: {
    parts: { text: string; href: string; tip: string; isLink: boolean }[];
    icon: string;
    bars: ReturnType<typeof bar>[];
    badge: string;
    badgeTip: string;
    badgeCss: string;
    css: string;
  }[] = [];
  const nodes: { title: string; sub: string; icon: string; iconColor: string; tip: string; iconCss: string; textCss: string; badge: string; badgeCss: string; css: string }[] = [];
  const notes: { text: string; css: string }[] = [];
  const hosp: { href: string; color: string; tip: string; css: string }[] = [];
  const hospText: { text: string; tip: string; css: string }[] = [];
  const labels: { text: string; tip: string; css: string }[] = [];
  const access: string[] = [];
  const aheads: string[] = [];
  const tiesOn: string[] = [];
  const tiesOff: string[] = [];
  const headsOn: string[] = [];
  const headsOff: string[] = [];
  const track: string[] = [];
  const shortfall: string[] = [];
  const filled: string[] = [];
  rows.forEach((r) => {
    const sys = r.sys;
    const mode = MODES[String(value(sys, 'mode'))];
    const parts = sys.href
      ? [{ text: sys.name, href: sys.href, tip: 'Source of its normal daily use: ' + sys.tip, isLink: true }]
      : [{ text: sys.name, href: '', tip: '', isLink: false }];
    util.push({
      parts,
      icon: sys.cap > 0 ? ICONS.drop : ICONS.tap,
      bars: r.bars.map(bar),
      badge: mode ? mode.text : '',
      badgeTip: mode ? mode.tip : '',
      badgeCss: mode ? 'background: ' + mode.bg + ';' : 'display: none;',
      css: 'left: ' + px(UX) + '; top: ' + px(r.y) + '; width: ' + px(UW) + '; height: ' + px(r.H) + '; border: 1.5px ' + (r.reached ? 'solid' : 'dashed') + ' ' + GREY + ';',
    });
    if (r.reached) {
      access.push(curve(AGX, AGY, UX - 2, r.accessY));
      aheads.push(head(UX - 1, r.accessY));
    }
    if (sys.people > 0) {
      const advised = num(sys, 'adv') === 1;
      let tip = 'The homes and businesses that ' + sys.name + ' serves.';
      if (advised && now !== null) {
        const pts = res.flows[sys.id].adv;
        let start: number | null = null;
        let end: number | null = null;
        pts.forEach((q, i) => {
          if (q[0] <= now && q[1] === 1 && (i === 0 || pts[i - 1][1] !== 1)) start = q[0];
          if (q[0] > now && q[1] === 0 && end === null) end = q[0];
        });
        tip = 'Under a boil-water advisory from ' + when(start ?? 0) + ' after the attack' + (end === null ? '.' : ' to ' + when(end) + '.');
      }
      nodes.push({
        title: count(sys.people),
        sub: 'people',
        icon: ICONS.home,
        iconColor: advised ? ORANGE : BLUE,
        tip,
        iconCss: 'top: ' + px(r.H / 2 - 11) + ';',
        textCss: 'top: ' + px(r.H / 2 - 17) + ';',
        badge: 'Boil water',
        badgeCss: advised ? '' : 'display: none;',
        css: 'left: ' + px(HX) + '; top: ' + px(r.y) + '; width: ' + px(HW) + '; height: ' + px(r.H) + '; border: 1.5px solid ' + (advised ? '#E7A777; background: #FFF6EF;' : '#C9CED6;'),
      });
      // The water delivered now, out of the stored water, against the homes' normal use.
      const gy = r.y + TOP + (r.bars.length - 1) * BP + BH / 2;
      const del = num(sys, 'del');
      const use = sys.use;
      const short = del < use * 0.999;
      const share = use > 0 ? Math.max(0, Math.min(1, del / use)) : 0;
      const x0 = UX + UW + 4;
      const x1 = HX - 4;
      (short ? shortfall : track).push(gauge(x0, x1, gy, 1));
      if (share > 0) filled.push(gauge(x0, x1, gy, short ? share : 1));
      labels.push({
        text: '',
        tip: 'Delivered to its homes: ' + amount(del) + ' of the ' + amount(use) + ' million gallons a day they normally use.',
        css: 'left: ' + px(x0) + '; width: ' + px(x1 - x0) + '; top: ' + px(gy - AHH) + '; height: ' + px(2 * AHH) + ';',
      });
    } else {
      notes.push({ text: 'No homes of its own here', css: 'left: ' + px(HX) + '; top: ' + px(r.y + r.H / 2 - 8) + '; width: ' + px(HW) + ';' });
    }
    if (sys.hospitals.length) {
      const hs = now === null ? res.before.hospitals[sys.id] : String(sample(res.hospitals[sys.id], now, false));
      const words = place.hospital_states[hs] || hs;
      const hy = r.y + r.H + 5;
      const n = sys.hospitals.length;
      const PER = Math.floor((HW + 4) / 18);
      const many = n > PER;
      const shown = many ? sys.hospitals.slice(0, PER - 2) : sys.hospitals;
      shown.forEach((h, k) => {
        hosp.push({
          href: h.href,
          color: HCOLORS[hs] || GREY,
          tip: h.name + ': ' + words + '. Its water comes from ' + sys.name + '. Opens its Medicare Care Compare page.',
          css: 'left: ' + px(HX + k * 18) + '; top: ' + px(hy) + ';',
        });
      });
      if (many) {
        const rest = sys.hospitals.slice(PER - 2);
        hospText.push({
          text: '+' + rest.length + ' more',
          css: 'left: ' + px(HX + (PER - 2) * 18) + '; top: ' + px(hy) + '; font-weight: 600; color: #3A414B;',
          tip: rest.map((h) => h.name).join('; ') + ': ' + words + '.',
        });
      } else if (n * 18 + 64 <= HW) {
        hospText.push({ text: n === 1 ? '1 hospital' : n + ' hospitals', tip: '', css: 'left: ' + px(HX + n * 18 + 2) + '; top: ' + px(hy) + '; color: #5A6270;' });
      }
    }
  });
  found.lanes.forEach((g) => {
    const a = rows[g.seller];
    const b = rows[g.buyer];
    const rate = Number(now === null ? res.before.ties[g.t.id] : sample(res.ties[g.t.id], now, false));
    const y0 = exitY(a, g.ia);
    const y1 = entryY(b, g.ib);
    const on = rate > 0.005;
    const tip = a.sys.name + ' sells ' + b.sys.name + ' ' + amount(rate) + ' million gallons a day now, of up to ' + amount(g.t.capacity) + '.';
    (on ? tiesOn : tiesOff).push('M ' + (UX - 1) + ' ' + r1(y0) + ' H ' + g.x + ' V ' + r1(y1) + ' H ' + (UX - 6));
    (on ? headsOn : headsOff).push(head(UX - 1, y1));
    labels.push({
      text: amount(rate),
      tip,
      css: 'left: ' + px(g.x + 4) + '; top: ' + px(y1 - 14) + '; width: ' + px(UX - g.x - 12) + '; font-weight: 600; color: ' + (on ? BLUE : GREY) + ';',
    });
    labels.push({ text: '', tip, css: 'left: ' + px(g.x - 4) + '; top: ' + px(Math.min(y0, y1)) + '; width: 8px; height: ' + px(Math.abs(y1 - y0)) + ';' });
  });
  const anyHosp = rows.some((r) => r.sys.hospitals.length);
  const legend = ['ok', 'degraded', 'failed'].map((k) => ({ text: place.hospital_states[k] || k, css: 'background: ' + HCOLORS[k] + ';' }));
  return {
    access: access.join(' '),
    accessHeads: aheads.join(' '),
    tiesOn: tiesOn.join(' '),
    tiesOff: tiesOff.join(' '),
    headsOn: headsOn.join(' '),
    headsOff: headsOff.join(' '),
    arrowTrack: track.join(' '),
    arrowShort: shortfall.join(' '),
    arrowFill: filled.join(' '),
    util,
    nodes,
    notes,
    hosp,
    hospText,
    labels,
    legend,
    legendCss: anyHosp ? 'top: 478px;' : 'display: none;',
  };
}
