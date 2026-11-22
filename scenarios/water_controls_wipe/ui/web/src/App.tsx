import { useEffect, useState } from 'react';
import { reading, when } from './format';
import { borders, nation, project } from './geo';
import { spread } from './map';
import type { Frame, Place, Summary } from './types';

async function get<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error ?? data.errors?.[0]?.message ?? 'The reading could not be loaded.');
  return data;
}
const areaMetrics = [
  ['restored_share', 'Normal water service'],
  ['people_interrupted_now', 'Residents without normal service'],
  ['people_under_advisory', 'Residents under advisory'],
  ['person_days_lost', 'Cumulative interruption'],
  ['unserved_volume', 'Water not supplied'],
  ['hospital_hours_constrained', 'Hospital service constraints'],
  ['economic_loss', 'Economic loss'],
  ['support.accepted', 'Regional support batches received'],
  ['support.filtered', 'Batch notices filtered'],
  ['relief.throughput', 'Dispatch capacity for households and hospitals'],
  ['support.reserved', 'Dispatch capacity reserved for regional casework'],
  ['emergency_water_deficit', 'Unmet household emergency water'],
  ['support.waiting', 'Outstanding regional dispatch work'],
  ['support.completed', 'Completed regional dispatch work'],
  ['support.delivered', 'Supplemental emergency water dispatched'],
];

function LocationMap({
  places,
  current,
  choose,
}: {
  places: Summary[];
  current: string;
  choose: (name: string) => void;
}) {
  const points = places.flatMap((p) => {
    const xy = project(p.key);
    return xy ? [{ ...p, x: xy[0], y: xy[1] }] : [];
  });
  return (
    <svg
      className="location-map"
      viewBox="0 0 975 610"
      aria-label="Choose a service area on the United States map"
    >
      <path d={nation} fill="#dbe9e6" />
      <path d={borders} stroke="white" strokeWidth="2" fill="none" />
      {spread(points, 1, 0, 10).map((m) => (
        <g
          key={m.p.key}
          className="region"
          role="button"
          tabIndex={0}
          aria-label={m.p.name}
          aria-pressed={m.p.key === current}
          onClick={() => choose(m.p.key)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              choose(m.p.key);
            }
          }}
        >
          <line x1={m.ax} x2={m.x} y1={m.ay} y2={m.y} stroke="#325b59" />
          <circle
            cx={m.x}
            cy={m.y}
            r={m.p.key === current ? 12 : 8}
            stroke="white"
            strokeWidth="2.5"
            fill={m.p.key === current ? '#b04e22' : '#256860'}
          />
          <title>{m.p.name}</title>
        </g>
      ))}
    </svg>
  );
}

function History({ frame, path, selected }: { frame: Frame; path: string; selected: number }) {
  const values = frame.readings[path].values;
  const width = 640,
    height = 84;
  const pts = values.map((value, i) => [
    (width * frame.hours[i]) / (frame.horizon || 1),
    height * (1 - Math.min(1, Math.max(0, value))),
  ]);
  return (
    <figure>
      <figcaption>Normal service over the study period</figcaption>
      <svg
        viewBox={`-37 -5 ${width + 40} ${height + 10}`}
        role="img"
        aria-label="Six-hour samples of the share receiving normal service"
      >
        <text x="-6" y="4" textAnchor="end" fontSize="10" fill="#52695f">
          100%
        </text>
        <text x="-6" y={height} textAnchor="end" fontSize="10" fill="#52695f">
          0%
        </text>
        <path d={`M0 ${height} H${width} M0 0 H${width}`} stroke="#d3ded8" strokeWidth="1" fill="none" />
        <polyline
          points={pts.map((p) => p.join(',')).join(' ')}
          stroke="#24685e"
          strokeWidth="2"
          fill="none"
        />
        <line
          x1={(width * selected) / (frame.horizon || 1)}
          x2={(width * selected) / (frame.horizon || 1)}
          y1="0"
          y2={height}
          stroke="#b04e22"
          strokeDasharray="3 3"
        />
      </svg>
      <div className="axis">
        <span>0 h</span>
        <span>{when(frame.horizon)}</span>
      </div>
    </figure>
  );
}

export default function App() {
  const [locations, setLocations] = useState<Summary[]>([]);
  const [key, setKey] = useState('');
  const [place, setPlace] = useState<Place | null>(null);
  const [run, setRun] = useState('');
  const [utility, setUtility] = useState('');
  const [history, setHistory] = useState<Frame | null>(null);
  const [point, setPoint] = useState<Frame | null>(null);
  const [index, setIndex] = useState(0);
  const [hour, setHour] = useState('0');
  const [asked, setAsked] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  function onError(e: Error) {
    if (e.name !== 'AbortError') setError(e.message);
  }
  useEffect(() => {
    const c = new AbortController();
    get<{ places: Summary[] }>('/api/places', c.signal)
      .then((data) => {
        setLocations(data.places);
        setKey(data.places[0]?.key ?? '');
      })
      .catch(onError);
    return () => c.abort();
  }, []);
  useEffect(() => {
    if (!key) return;
    const c = new AbortController();
    setPlace(null);
    setRun('');
    setHistory(null);
    setUtility('');
    setError('');
    get<Place>('/api/places/' + key, c.signal)
      .then((p) => {
        setPlace(p);
        setRun(p.featured);
      })
      .catch(onError);
    return () => c.abort();
  }, [key]);
  const base =
    place && place.key === key && run ? '/api/places/' + key + '/runs/' + encodeURIComponent(run) : '';
  useEffect(() => {
    setHistory(null);
    setPoint(null);
    setIndex(0);
    setHour('0');
    setAsked(null);
    setPlaying(false);
    setError('');
    if (!base) return;
    const c = new AbortController();
    get<Frame>(base, c.signal).then(setHistory).catch(onError);
    return () => c.abort();
  }, [base]);
  useEffect(() => {
    setPoint(null);
    if (!base || asked === null) return;
    const c = new AbortController();
    get<Frame>(base + '?hour=' + encodeURIComponent(asked), c.signal)
      .then(setPoint)
      .catch(onError);
    return () => c.abort();
  }, [base, asked]);
  useEffect(() => {
    if (!playing || !history) return;
    if (index >= history.hours.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setIndex(index + 1);
      setHour(String(history.hours[index + 1]));
    }, 140);
    return () => window.clearTimeout(timer);
  }, [index, playing, history]);
  const displayed = asked === null ? history : point;
  const i = asked === null ? index : 0;
  const now = displayed?.hours[i] ?? 0;
  const metrics = utility
    ? [
        [utility + '.service', 'Normal service'],
        [utility + '.delivered', 'Cumulative water delivered'],
      ]
    : areaMetrics;
  return (
    <main>
      <header>
        <h1>Water service recovery</h1>
        <p>Simulated service and response for the selected area.</p>
      </header>
      <div className="layout">
        <aside>
          <h2>Service area</h2>
          <label>
            Place
            <select value={key} onChange={(e) => setKey(e.target.value)}>
              {locations.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <LocationMap places={locations} current={key} choose={setKey} />
          {place && place.key === key && (
            <>
              <label>
                Response run
                <select value={run} onChange={(e) => setRun(e.target.value)}>
                  {place.runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Utility
                <select value={utility} onChange={(e) => setUtility(e.target.value)}>
                  <option value="">Whole service area</option>
                  {place.systems.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
        </aside>
        <section aria-busy={!history}>
          <h2>{place?.name ?? 'Service readings'}</h2>
          {error && <p role="alert">{error}</p>}
          {!history && !error && <p role="status">Loading the selected response…</p>}
          {history && place && (
            <>
              <History
                frame={history}
                path={utility ? utility + '.service' : 'restored_share'}
                selected={asked ?? history.hours[index]}
              />
              <div className="clock">
                <button
                  type="button"
                  onClick={() => {
                    setAsked(null);
                    if (index === history.hours.length - 1) {
                      setIndex(0);
                      setHour('0');
                    }
                    setPlaying(!playing);
                  }}
                >
                  {playing ? 'Pause' : 'Play'}
                </button>
                <input
                  aria-label="Study time, six-hour samples"
                  type="range"
                  min="0"
                  max={history.hours.length - 1}
                  value={index}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setPlaying(false);
                    setAsked(null);
                    setIndex(next);
                    setHour(String(history.hours[next]));
                  }}
                />
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    setPlaying(false);
                    setError('');
                    const selected = Number(hour);
                    const after = history.hours.findIndex((t) => t > selected);
                    setIndex(after < 0 ? history.hours.length - 1 : Math.max(0, after - 1));
                    setAsked(selected);
                  }}
                >
                  <label>
                    Hour
                    <input
                      type="number"
                      min="0"
                      max={history.horizon}
                      step="any"
                      required
                      value={hour}
                      onChange={(e) => setHour(e.target.value)}
                    />
                  </label>
                  <button>Read</button>
                </form>
              </div>
              {displayed ? (
                <>
                  <h3>Readings at {when(now)}</h3>
                  <dl>
                    {metrics.map(([path, label]) => {
                      const series = displayed.readings[path];
                      return (
                        <div key={path}>
                          <dt>{label}</dt>
                          <dd>{reading(series.values[i], series.unit)}</dd>
                        </div>
                      );
                    })}
                  </dl>
                </>
              ) : (
                <p role="status">Reading the selected hour…</p>
              )}
              <p className="revision">
                Current model revision <code>{history.model_hash.slice(0, 12)}</code>. The chart samples every
                six hours. The hour field reads the recorded state directly.
              </p>
            </>
          )}
        </section>
      </div>
      <footer>
        Scenario estimates. Archived publications from revision <code>8488047</code> describe the earlier
        model.
      </footer>
    </main>
  );
}
