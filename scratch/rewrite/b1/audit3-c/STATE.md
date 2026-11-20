# Audit 3b, agent C: a moment's own changes, every reader, a switch at a moment

Brief: COMMON-B, audit3b part C, audit3 "What every agent does"; PLAN 10, 24-26; spec.md:542-544.
L works in /home/user/napkin-L (sharing: network, sparse, declared, plan, oracle network.py).

## Status
- [x] read briefs, T's STATE, repros (clock.py, coincide.py reproduce on HEAD bbfad12)
- [ ] places listed (below, in progress)  - [ ] rule test, failing on HEAD  - [ ] fixes  - [ ] final runs

## Findings so far (HEAD bbfad12)
- coincide: not only at a moment. A component's segment that STARTS a roundoff short of a switch it
  crosses fails (Radau: FD Jacobian straddles the switch): stage 0.5 h, `1 if water < 2 else 3`
  fails at the located root 1.9999999996 h (state 1.9999999999999996). Sparse fails at 2 L at 2 h too.
- oracle bug (network.motion, L's file): at a moment the settle is in instant mode, the motion
  after carries those rates: `1 L/h if t <= 2 h else 3 L/h` carries 1 L/h after 2 h forever (water
  3, 4 at 3, 4 h; exact: 5, 8; engine right). Any closed comparison crossed from its closed side.
- engine rate_at at a moment reads the instant side, roundoff-dependent for a store switch.
- MAIN SESSION (msg): the oracle's "rates after a moment = the instant's" is L's item 1 (one rule:
  the rates over the interval after a moment are those of the state just after it); L fixes it in
  the oracle and the engine. I do NOT edit tests/reference/network.py, nor build a germ settle in
  the oracle. Keep such cases in the rule test; list here which wait for L.
- item 2 on HEAD (scratchpad p2.py): two firings at 1 h, the first starts a pipe at the tank, the
  second captures / passes tank.main.actual_rate: both read the stale 2 L/h silently; a delay of
  the second reads it at the firing in the engine (stage at 3 h) but waits for the settling in the
  oracle (2 h); an assertion over the outflow after the firings fails in the oracle only.

## Places (cause 1: the clock at a moment) ...
## Places (cause 2: every reader) ...
## Places (cause 3: a segment that starts at a switch) ...
## Decisions ...
## For L / the main session ...
## For the owner ...
