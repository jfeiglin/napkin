// The data that the engine's server sends (../../server.py, ../../view.py).

export type Series<T = number> = [number, T][];

export interface Hospital {
  name: string;
  ccn: string;
  href: string;
}

export interface Fixed {
  use: number;
  cap: number;
  bought: number;
  sold: number;
  full: number;
  icap: number;
}

export interface System extends Fixed {
  id: string;
  name: string;
  href: string;
  tip: string;
  people: number;
  buys: string[];
  sells: string[];
  hospitals: Hospital[];
  hospital_entity: string;
  facilities: number;
}

export interface Tie {
  id: string;
  seller: string;
  buyer: string;
  capacity: number;
}

export interface Place {
  id: string;
  key: string;
  name: string;
  title: string;
  package: string;
  what: string;
  people: number;
  systems: System[];
  ties: Tie[];
  runs: { id: string; name: string }[];
  featured: string;
  hospital_states: Record<string, string>;
  outputs: Record<string, string>;
}

export interface Summary {
  id: string;
  key: string;
  name: string;
  title: string;
  systems: number;
  people: number;
  hospitals: number;
}

export interface Flows {
  prod: Series;
  imp: Series;
  stored: Series;
  del: Series;
  adv: Series;
  ctl: Series<string>;
  mode: Series<string>;
}

export interface Moment {
  t: number;
  text: string;
  times: number;
  last: number;
}

export interface Frame {
  run: string;
  name: string;
  actor: string;
  t_end: number;
  horizon: number;
  peak: number;
  back: number | null;
  advisory_end: number | null;
  person_days: number;
  econ: number;
  hospital: number;
  unserved: number;
  out: Series;
  adv: Series;
  moments: Moment[];
  fixed: Record<string, Fixed>;
  before: {
    flows: Record<string, { prod: number; imp: number; stored: number; del: number; adv: number; ctl: string; mode: string }>;
    ties: Record<string, number>;
    hospitals: Record<string, string>;
  };
  flows: Record<string, Flows>;
  ties: Record<string, Series>;
  hospitals: Record<string, Series<string>>;
}

// One point of the map: a place where it is on the map's frame.
export interface Point {
  key: string;
  name: string;
  systems: number;
  x: number;
  y: number;
}
