# Deterministic scenario capability inventory

Each calculation is defined by its own folder: its model, evidence, units and independent checks.
The [scenario catalogue](../README.md) lists the available cases. Each folder's README
states its mechanism family. The table below describes the mathematical requirements shared by
those families.

## Families and mathematical requirements

| Family | Required representation | Essential checks |
| --- | --- | --- |
| Thermal exposure | Finite susceptible/protected cohorts, time-varying exposure, competing transitions, restoration | Nonnegative cohorts; stable zero/tiny hazard; conservation; unique casualty accounting |
| Clinical continuity | Separate patient cohorts, service deficit, complete-treatment episodes and clinical deadlines | Disjoint denominators; explicit outcome status; declared service-to-health transfer |
| Contaminated exposure | Finite susceptible consumers, exposure episodes, incident cases, delayed outcomes | Unique infections/consumers distinct from visits or doses; survivor conservation |
| Supply and funding | Conserved stocks, finite incoming supply, allocation, demand, replacement and funding ledgers | Demand caps; explicit diversion/sinks; unique spending and patient accounting |
| Restoration and verification queues | Fluid backlog or finite identified demand cohorts, processing capacity, rework and recovery | Explicit queue discipline; cumulative completion distinct from unique restored assets; capped recapture |
| Service and verification impairment | Functionality signals, partial service, restoration and typed unknown outputs | Correct state/health display; finite valid dynamics; explicit incomplete metric status |
| Causal adversary interference | Shared defender responses, attacker events that act once on a schedule or on an observed defender step, capability factors/ceilings, explicit access and integrity states | Degradation respects the nominal capability ceiling; attempted-use detection; stopped and skipped outcomes and the order of one moment; containment distinct from repair |
| Warning, movement and treatment deadlines | Hazard following the initiating cyber effect, warning and response events, finite movement/treatment capacity, deadline snapshots | Same-time order and inclusive boundaries; an outcome that succeeds satisfies its stated eligibility; multiyear survivor accounting |

## Cyber initiation

A scenario belongs in this catalogue when its initiating event is a cyber event and that
premise carries evidence. The event `start` of the attacker is the first move. It fires first, at
hour zero, and its records support the access that the run starts from. Its lines name the things
that it reaches.

The records of the first move cite the incidents and the ATT&CK techniques with their library
claims. The premise `START` of the notes (`notes:`, `premises:`) states the limits of what those
claims establish. These are the catalogue's conventions, and the language gives them no meaning.
The methods page gives the limits after the effect of the attack, so it fails for a scenario that
has a start but no `START` premise.

The start of an incident has lines of its own: the first change of the run, at hour zero. Each run
checks that the start fires first. The start of an operation has no lines: it is a moment at hour
zero that changes nothing, from which the attacker's events time their moves, with `after`. Such an
event ends as done, stopped or skipped like any other event with several outcomes; when it ends as
stopped or skipped, the service accounting stays at its starting point
([language](../../docs/language.md#26-events)).

The builder writes the start as the model's `initiation` record. The evidence coverage report
(`python -m tools.evidence.integrate --coverage`) lists the claims that the records of the start
and of its outcome cite, each with its status.

## Supported class and extension boundary

The scenario language, version 0.0.1, targets finite deterministic hybrid models. The things of a
model are each made from a template or without one. A thing holds typed values: inputs, fixed
values, named, yes/no and number states, stocks, tallies and formulas. Events change these values
at one moment, with explicit nonnegative moves, and each takes one of its outcomes by their chances.
Flows act all the time, shares divide stocks, and a `when` watches only the supported crossings.

The builder (`napkin/model/`) turns a file into the flat structures that
[the engine](../../docs/engine.md) runs, and compilation admits expressions and `when` conditions with the
documented proofs. Options set the start states and inputs of each run, and the runs combine them;
the builder makes one structure for each set of options that set start states that the runs use.

Each option of the group `Response`, which `choice_group` names in `brief.toml`, sets the activation and capacity inputs
that every run with that response shares. The attacker's events and its capability inputs use the
same mathematical core as every other part, with explicit access states, events that wait (`after`)
and `sees`, the facts that an actor observes. An event with `once` happens at most once in a run;
an event without it fires each time its condition becomes true.

Continuous threshold detection covers two classes of crossing ([the engine](../../docs/engine.md#triggers)): a
quantity whose rate, and the rates and capacities of the flows that move it, change only at moments;
and a stock that reaches zero in a closed network of flows whose rates read its stocks only by
comparing them with zero. A `when:` joins any clocks with at most one crossing. A condition that
compares stocks with zero joins no clock and no crossing.

Conservative finite stock components admit exact zero-boundary detection. Stock-face conditions
and tests of named states receive bounded composition proofs. Incoming supply releases an empty
stock under a finite positive-side field; reserve withdrawals resume from rebuilt inventory. A
`when:` on a closed stock face records the boundary that it reaches. Repayment tails, flows that
move cash and debt together, use the proved cash/debt reserve relationship and preserve all
transaction legs.

Report sampling is independent of the solver. Reporting lags (an output's `lag:`) operate on
measures, including impulses. Feedback delays use explicit finite pending cohorts and transitions.
Model expressions use the typed deterministic expression language. Event admission uses
scheduled events and proved crossings.

Fluid queues represent amounts and conservation. Per-person timing uses identified
finite demand cohorts with declared eligibility and deadlines. A future primitive must define its
typed inputs, conservation and domain conditions, event semantics, evidence records,
independent reference cases and failure behavior before it is admitted.

The measure of each output (`measure:`) governs its invariants: cumulative deaths and unique cases
never fall (tallies); living stocks and backlogs track their current inventory (`level`). Recapture
reduces net cumulative loss within its eligible earlier-loss ceiling. An output that is not
estimated (`unestimated:`) carries its reason and scope. Explicit nonnegative contributions support
a project-scale lower bound.

Independent checks cover each scenario's resource commitments, event clocks, clinical conversions
and economic accounts. Each scenario owns its oracle input map and scenario assertions. The
central suites discover available folders and exercise shared properties. Scientific
interpretation follows each scenario's effective inputs, evidence records, source applicability and
outcome scopes.
