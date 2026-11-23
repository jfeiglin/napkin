// The board: the map of the places or the water systems of one place, the story of a run under it, and the
// panel of the place, the run, the time and the moments. Each place and run comes from the engine's server,
// which runs the engine when the page first asks for it.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { chart } from './chart';
import { count, css, dollars, when } from './format';
import { borders, nation, project } from './geo';
import { graph } from './graph';
import { mapLayout } from './map';
import type { Frame, Place, Point, Summary } from './types';

const WIDTH = 1440;
const HEIGHT = 980;

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok) {
    const errors = (body.errors ?? []).map((e: { message: string }) => e.message).join(' ');
    throw new Error(body.error ?? (errors || 'The server answered ' + response.status + '.'));
  }
  return body as T;
}

interface Chosen {
  key: string;
  run: string | null;
}

export default function App() {
  const [summaries, setSummaries] = useState<Summary[] | null>(null);
  const [places, setPlaces] = useState<Record<string, Place>>({});
  const [frames, setFrames] = useState<Record<string, Frame>>({});
  const [wanted, setWanted] = useState<Chosen | null>(null);
  const [shown, setShown] = useState<{ key: string; run: string } | null>(null);
  const [view, setView] = useState<'map' | 'graph'>('map');
  const [t, setT] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    const fit = () => setScale(Math.min(1, window.innerWidth / WIDTH));
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, []);

  // The places, and the one with the most water systems first.
  useEffect(() => {
    get<{ places: Summary[] }>('/api/places')
      .then((d) => {
        setSummaries(d.places);
        const first = d.places.reduce((a, b) => (b.systems > a.systems ? b : a), d.places[0]);
        setWanted({ key: first.key, run: null });
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  // The place and the run that the reader chose, from the server: the run is ready when its frame is.
  useEffect(() => {
    if (!wanted) return;
    const abort = new AbortController();
    (async () => {
      const place = places[wanted.key] ?? (await get<Place>('/api/places/' + wanted.key, abort.signal));
      if (!places[wanted.key]) setPlaces((p) => ({ ...p, [wanted.key]: place }));
      const ids = place.runs.map((r) => r.id);
      const run = wanted.run && ids.includes(wanted.run) ? wanted.run : place.featured;
      const id = wanted.key + '/' + run;
      const found = frames[id] ?? (await get<Frame>('/api/places/' + wanted.key + '/runs/' + run, abort.signal));
      if (!frames[id]) setFrames((f) => ({ ...f, [id]: found }));
      setShown({ key: wanted.key, run });
      setError(null);
    })().catch((e) => {
      if (e.name !== 'AbortError') setError(String(e.message ?? e));
    });
    return () => abort.abort();
    // The caches are read, not watched: a change of the choice starts a request.
  }, [wanted]);

  const stop = useCallback(() => {
    if (timer.current !== null) {
      clearInterval(timer.current);
      timer.current = null;
    }
    setPlaying(false);
  }, []);
  useEffect(() => stop, [stop]);

  const choose = (key: string, run: string | null) => {
    stop();
    setT(null);
    setWanted({ key, run });
  };

  const points: Point[] = useMemo(
    () =>
      (summaries ?? []).flatMap((s) => {
        const xy = project(s.key);
        return xy ? [{ key: s.key, name: s.name, systems: s.systems, x: xy[0], y: xy[1] }] : [];
      }),
    [summaries],
  );

  const place = shown ? places[shown.key] : undefined;
  const res = shown ? frames[shown.key + '/' + shown.run] : undefined;
  const busy = !!wanted && (!shown || wanted.key !== shown.key || (wanted.run !== null && wanted.run !== shown.run));
  const pending = wanted ? summaries?.find((s) => s.key === wanted.key) : undefined;

  const frame = { width: WIDTH, height: HEIGHT, transform: 'scale(' + scale + ')' };
  if (!place || !res) {
    return (
      <div className="wp-fit" style={{ height: HEIGHT * scale }}>
        <div className="wp-board" style={frame}>
          <p className="wp-wait">{error ? 'The view could not load: ' + error : 'Running the model for ' + (pending?.name ?? 'the places') + '…'}</p>
        </div>
      </div>
    );
  }

  const tEnd = res.t_end;
  const horizon = res.horizon;
  const now = t === null ? null : Math.min(t, horizon);

  const play = () => {
    stop();
    const step = tEnd / 140;
    let at = t === null || t >= tEnd ? 0 : t;
    setT(at);
    setPlaying(true);
    timer.current = window.setInterval(() => {
      at += step;
      if (at >= tEnd) {
        stop();
        setT(tEnd);
        return;
      }
      setT(at);
    }, 80);
  };

  // The tiles: the run's outcomes, and two clocks from its story.
  const beyond = 'Beyond ' + Math.round(horizon / 24) + ' days';
  const span = (h: number | null, none: string) => (h === null ? none : h >= horizon ? beyond : when(h));
  const L = place.outputs;
  const tiles = [
    { value: count(res.peak), label: 'Most people without normal water at once' },
    { value: span(res.back, 'No one'), label: 'Until everyone has normal water again' },
    { value: span(res.advisory_end, 'No advisory'), label: 'Until the last boil-water advisory ends' },
    { value: count(res.person_days), label: L.person_days_lost },
    { value: dollars(res.econ), label: L.economic_loss },
    { value: count(res.hospital), label: L.hospital_hours_constrained },
  ];

  const options = (summaries ?? []).slice().sort((a, b) => (a.name < b.name ? -1 : 1));
  const nSys = place.systems.length;
  const nTies = place.ties.length;
  const nHosp = place.systems.reduce((a, s) => a + s.hospitals.length, 0);
  const facts = [nSys + (nSys === 1 ? ' water system' : ' water systems')];
  if (nTies) facts.push(nTies + (nTies === 1 ? ' sale between them' : ' sales between them'));
  facts.push(count(place.people) + ' people');
  if (nHosp) facts.push(nHosp + (nHosp === 1 ? ' hospital' : ' hospitals'));

  let latest = -1;
  res.moments.forEach((m, i) => {
    if (now !== null && m.t <= now + 1e-9) latest = i;
  });

  const m = view === 'map' ? mapLayout(points, place.key) : null;
  const g = view === 'graph' ? graph(place, res, now) : null;
  const c = chart(place, res, now);
  const agentTip = view === 'map' ? 'Show the water systems of ' + place.name : 'Back to the map of the places';

  return (
    <div className="wp-fit" style={{ height: HEIGHT * scale }}>
      <div className={'wp-board' + (busy ? ' wp-busy' : '')} style={frame}>
        <div style={css('position: absolute; left: 40px; top: 32px; width: 780px;')}>
          <div className="wp-kicker">{place.name + ' · ' + res.name}</div>
          <div className="wp-title">{place.title.split(': ')[0]}</div>
          <div className="wp-tiles">
            {tiles.map((tile, i) => (
              <div key={i} className="wp-tile">
                <div className="wp-tile-value">{tile.value}</div>
                <div className="wp-tile-label">{tile.label}</div>
              </div>
            ))}
          </div>
        </div>

        {m && (
          <>
            <svg viewBox={m.mapBox} aria-hidden="true" style={{ position: 'absolute', ...css(m.mapCss) }}>
              <path d={nation} fill="#E9ECF0" stroke="none" />
              <path d={borders} fill="none" stroke="#FFFFFF" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
            <svg width={WIDTH} height={HEIGHT} viewBox={'0 0 ' + WIDTH + ' ' + HEIGHT} aria-hidden="true" className="wp-overlay">
              <path d={m.stemPath} fill="none" stroke="#16181D" strokeWidth="1" />
              <path d={m.anchorPath} fill="#16181D" stroke="none" />
              <path d={m.atkLine} fill="none" stroke="#E34948" strokeWidth="7" strokeOpacity="0.12" strokeLinecap="round" />
              <path d={m.atkLine} className="wp-attack" fill="none" stroke="#E34948" strokeWidth="1.8" strokeLinecap="round" />
              <path d={m.atkHead} fill="#E34948" stroke="none" />
            </svg>
            {m.dots.map((dot) => (
              <button key={dot.key} type="button" className="wp-dot" onClick={() => choose(dot.key, wanted?.run ?? null)} aria-label={dot.aria} title={dot.aria} style={css(dot.css)} />
            ))}
            {m.dotLabels.map((l) => (
              <div key={l.text} className="wp-dot-label" style={css(l.css)}>
                {l.text}
              </div>
            ))}
            <div className="wp-hint" style={css(m.hintCss)}>
              Choose a place on the map or in the list. Click the attack to see the place's water systems.
            </div>
          </>
        )}

        {g && (
          <div style={css('position: absolute; left: 40px; top: 176px; width: 780px; height: 540px;')}>
            <svg width="780" height="540" viewBox="0 0 780 540" aria-hidden="true" style={css('position: absolute; left: 0; top: 0;')}>
              <path d={g.access} fill="none" stroke="#E34948" strokeWidth="7" strokeOpacity="0.12" strokeLinecap="round" />
              <path d={g.access} className="wp-attack" fill="none" stroke="#E34948" strokeWidth="1.8" strokeLinecap="round" />
              <path d={g.accessHeads} fill="#E34948" stroke="none" />
              <path d={g.tiesOff} fill="none" stroke="#A8AEB7" strokeWidth="1.5" strokeDasharray="5 4" strokeLinejoin="round" />
              <path d={g.tiesOn} className="wp-sale" fill="none" stroke="#2A78D6" strokeWidth="1.6" strokeLinejoin="round" />
              <path d={g.headsOff} fill="#A8AEB7" stroke="none" />
              <path d={g.headsOn} fill="#2A78D6" stroke="none" />
              <path d={g.arrowTrack} fill="#E6EAEF" stroke="none" />
              <path d={g.arrowShort} fill="#FBE3D2" stroke="none" />
              <path d={g.arrowFill} fill="#2A78D6" stroke="none" />
            </svg>
            {g.util.map((u, i) => (
              <div key={i} className="wp-card" style={css(u.css)}>
                <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" style={css('position: absolute; left: 9px; top: 5px;')}>
                  <path d={u.icon} fill="none" stroke="#2A78D6" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div className="wp-card-name">
                  {u.parts.map((q, k) =>
                    q.isLink ? (
                      <a key={k} href={q.href} target="_blank" rel="noopener" title={q.tip} className="wp-source">
                        {q.text}
                      </a>
                    ) : (
                      <span key={k}>{q.text}</span>
                    ),
                  )}
                </div>
                <div title={u.badgeTip} className="wp-badge" style={css(u.badgeCss)}>
                  {u.badge}
                </div>
                {u.bars.map((b, k) => (
                  <div key={k} title={b.tip} style={{ position: 'absolute', height: 15, ...css(b.css) }}>
                    <div className="wp-track" style={css(b.trackCss)}>
                      <div className="wp-bar-text" style={{ ...css(b.textCss), ...css(b.inCss) }}>
                        {b.caption}
                      </div>
                      <div className="wp-fill" style={css(b.fill)}>
                        <div className="wp-bar-text" style={{ color: '#FFFFFF', ...css(b.inCss) }}>
                          {b.caption}
                        </div>
                      </div>
                    </div>
                    <div className="wp-bar-out" style={{ ...css(b.textCss), ...css(b.outCss) }}>
                      {b.caption}
                    </div>
                  </div>
                ))}
              </div>
            ))}
            {g.nodes.map((n, i) => (
              <div key={i} title={n.tip} className="wp-card" style={css(n.css)}>
                <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" style={{ position: 'absolute', left: 9, ...css(n.iconCss) }}>
                  <path d={n.icon} fill="none" stroke={n.iconColor} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div style={{ position: 'absolute', left: 35, right: 8, ...css(n.textCss) }}>
                  <div className="wp-node-title">{n.title}</div>
                  <div className="wp-node-sub">{n.sub}</div>
                </div>
                <div className="wp-badge" style={{ background: '#C2610C', ...css(n.badgeCss) }}>
                  {n.badge}
                </div>
              </div>
            ))}
            {g.notes.map((n, i) => (
              <div key={i} className="wp-note" style={css(n.css)}>
                {n.text}
              </div>
            ))}
            {g.hosp.map((h, i) => (
              <a key={i} href={h.href} target="_blank" rel="noopener" title={h.tip} aria-label={h.tip} className="wp-hospital" style={css(h.css)}>
                <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" style={{ display: 'block' }}>
                  <rect x="0.5" y="0.5" width="13" height="13" rx="3.5" fill={h.color} />
                  <path d="M 7 3.6 V 10.4 M 3.6 7 H 10.4" stroke="#FFFFFF" strokeWidth="1.9" strokeLinecap="round" />
                </svg>
              </a>
            ))}
            {g.hospText.map((h, i) => (
              <div key={i} title={h.tip} className="wp-hospital-text" style={css(h.css)}>
                {h.text}
              </div>
            ))}
            {g.labels.map((l, i) => (
              <div key={i} title={l.tip} className="wp-label" style={css(l.css)}>
                {l.text}
              </div>
            ))}
            <div className="wp-legend" style={css(g.legendCss)}>
              <div className="wp-legend-title">Hospitals</div>
              {g.legend.map((k) => (
                <div key={k.text} className="wp-legend-row">
                  <span className="wp-legend-key" style={css(k.css)} />
                  {k.text}
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          type="button"
          className="wp-agent"
          onClick={() => setView(view === 'map' ? 'graph' : 'map')}
          aria-pressed={view === 'graph'}
          aria-label={agentTip}
          title={agentTip}
          style={{ left: 40, top: 190 }}
        >
          <svg width="64" height="64" viewBox="-32 -32 64 64" aria-hidden="true">
            <defs>
              <clipPath id="wp-hk-clip">
                <circle cx="0" cy="0" r="24" />
              </clipPath>
            </defs>
            <circle cx="0" cy="0" r="31" fill="#E34948" fillOpacity="0.10" />
            <circle cx="0" cy="0" r="24" fill="#16181D" />
            <g clipPath="url(#wp-hk-clip)">
              <path d="M -18 27 C -18 8 -13 -14 0 -16.5 C 13 -14 18 8 18 27 Z" fill="#474D57" />
              <ellipse cx="0" cy="-0.5" rx="9" ry="10.4" fill="#0B0C0E" />
            </g>
            <path
              d="M 0 -6.5 C 0.7 -2.2 1.7 -1.2 5.5 -0.5 C 1.7 0.2 0.7 1.2 0 5.5 C -0.7 1.2 -1.7 0.2 -5.5 -0.5 C -1.7 -1.2 -0.7 -2.2 0 -6.5 Z"
              fill="#FF6B6A"
            />
            <circle cx="0" cy="0" r="24" fill="none" stroke="#E34948" strokeWidth="1.5" />
          </svg>
        </button>
        <div className="wp-agent-label">{res.actor}</div>

        <div className="wp-story">
          <div className="wp-story-legend">
            <span className="wp-story-title">Over the story</span>
            <span className="wp-key">
              <span className="wp-key-area" />
              {c.outText}
            </span>
            <span className="wp-key">
              <span className="wp-key-line" />
              {c.advText}
            </span>
          </div>
        </div>
        <svg width={WIDTH} height={HEIGHT} viewBox={'0 0 ' + WIDTH + ' ' + HEIGHT} aria-hidden="true" className="wp-overlay">
          <path d={c.grid} fill="none" stroke="#E3E6EA" strokeWidth="1" />
          <path d={c.area} fill="#2A78D6" fillOpacity="0.18" stroke="none" />
          <path d={c.out} fill="none" stroke="#2A78D6" strokeWidth="1.6" strokeLinejoin="round" />
          <path d={c.adv} fill="none" stroke="#C2610C" strokeWidth="1.6" strokeLinejoin="round" />
          <path d={c.ticks} fill="none" stroke="#8A9099" strokeWidth="1" />
          <path d={c.moments} fill="none" stroke="#16181D" strokeWidth="1" />
          <path d={c.play} fill="none" stroke="#16181D" strokeWidth="1.5" />
        </svg>
        {c.labels.map((a, i) => (
          <div key={i} className="wp-axis" style={css(a.css)}>
            {a.text}
          </div>
        ))}

        <div className="wp-panel">
          <div className="wp-panel-head">
            <div className="wp-place">{place.name}</div>
            <select value={wanted?.key ?? place.key} onChange={(e) => choose(e.target.value, wanted?.run ?? null)} aria-label="Choose a place" className="wp-select">
              {options.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
          <p className="wp-what">{place.what}</p>
          <div className="wp-facts">{facts.join(' · ')}</div>

          <div className="wp-views" role="group" aria-label="View">
            {(['map', 'graph'] as const).map((id) => (
              <button key={id} type="button" className={'wp-view' + (view === id ? ' on' : '')} onClick={() => setView(id)} aria-pressed={view === id}>
                {id === 'map' ? 'Map of the places' : 'The water systems'}
              </button>
            ))}
          </div>

          <div className="wp-section">Response</div>
          <div className="wp-runs" role="group" aria-label="Response">
            {place.runs.map((r) => (
              <button key={r.id} type="button" className={'wp-btn' + (r.id === shown?.run ? ' on' : '')} onClick={() => choose(place.key, r.id)} aria-pressed={r.id === shown?.run}>
                {r.name}
              </button>
            ))}
          </div>

          <div className="wp-time">
            <button type="button" className="wp-btn wp-play" onClick={() => (playing ? stop() : play())}>
              {playing ? 'Pause' : 'Play'}
            </button>
            <input
              type="range"
              aria-label="Time since the attack"
              min="0"
              max="1000"
              step="1"
              value={now === null ? 0 : Math.round(Math.min(1, now / tEnd) * 1000)}
              onChange={(e) => {
                stop();
                setT((Number(e.target.value) / 1000) * tEnd);
              }}
              className="wp-slider"
            />
            <div className="wp-now">{now === null ? 'Before the attack' : when(now) + ' after the attack'}</div>
          </div>
          <div className="wp-status" aria-live="polite">
            {error ? 'The model could not run: ' + error : busy ? 'Running the model for ' + (pending?.name ?? place.name) + '…' : ''}
          </div>

          <div className="wp-moments">
            {res.moments.map((mo, i) => {
              const past = i <= latest;
              const later = mo.t > tEnd;
              const more = (mo.times > 1 ? ' (' + mo.times + ' times, the last at ' + when(mo.last) + ')' : '') + (later ? ' · after the story' : '');
              const whenText = when(mo.t) + (later ? ' · later' : '');
              return (
                <button
                  key={i}
                  type="button"
                  className={'wp-moment' + (past ? ' past' : '') + (i === latest ? ' latest' : '') + (later ? ' later' : '')}
                  onClick={() => {
                    stop();
                    setT(mo.t);
                  }}
                  aria-label={i + 1 + '. ' + whenText + ': ' + mo.text + more}
                >
                  <span className="wp-moment-n">{i + 1}</span>
                  <span className="wp-moment-when">{when(mo.t)}</span>
                  <span>
                    {mo.text}
                    <span className="wp-moment-more">{more}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
