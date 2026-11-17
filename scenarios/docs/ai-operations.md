# AI operations

Every case models an AI agent on the attacking side. This page explains what that means in the
model, and how the model runs the AI's own behaviour, not only a label for it. It also explains how
each case compares the AI with a skilled human team that runs the same operation. The
[scenario briefs](../README.md) tell each case as a story; this page is the contract behind
them. The [scenario language](../../docs/language.md) defines each line that it names.

## What the AI is, and what the scenario fixes

The AI is an agent that carries out cyber moves through the access and tools that the scenario
gives it. The scenario, not the AI, fixes its objective, the systems it can reach, what it can
observe and when it can act again (assumption `A-AI-CYBER-OPERATIONS`). In a scenario file the
attacker is the one thing with `role adversary`; the pages reject a second one. This attacker is a
synthetic example in the style of the language page ([§1](../../docs/language.md#1-a-scenario-file-in-one-page)),
whose values and sources are invented:

```text
# Its text says who it works for, what it aims at, what it reaches and what it can keep.
attacker:
    "An AI agent that works for a hostile group. It reaches the dosing controls through the
        plant's remote-support account."
    @assumption A-DEMO-ATTACK "Reported attacks on water utilities reached dosing controls through
        remote access. The scenario chooses how far this attack reaches, and when."
    role adversary
    sees access, operators.find, operators.remote, plant.dosing

    input actor = "The AI"
    var access: "none" | "kept" = "none"  @sees_reset
        "Hidden access after the first move"
    input reaction_time = 0.25 h in 0.05 h to 96 h  @ai_tempo
        "Attacker's time to act after the operators reset the dosing"

    # The first move. The attack's name is the `attack` line of the scenario block.
    event start when t >= 0 h:  @dosing_change
        "{actor} changes the chlorine dosing through the plant's remote-support account."
        plant.dosing = "tampered"

    # With hidden access, the attacker sees the reset and changes the dosing again.
    event tamper_again once after reaction_time when access is "kept" and count(operators.find) > 0:  @sees_reset @ai_tempo
        done operators.remote is "open" and plant.dosing is "normal":  @dosing_change
            "{actor} changes the dosing again after the reset."
            plant.dosing = "tampered"
        skipped operators.remote is "open" and plant.dosing is not "normal":
            "The dosing is under manual control, so the attacker cannot change it."
        stopped else:
            "The operators close the remote-support account before the attacker acts again."
            role operator

options "Access":
    "No hidden access":
        "The attacker keeps no access after its first move."
    "Keeps hidden access":
        "The attacker keeps hidden access, and changes the dosing again after the reset."
        attacker.access = "kept"  @sees_reset

options "Attacker":
    "AI agent":
        "An AI agent acts within minutes of the reset."
    "Human team":
        "A human team comes back about two days later."
        attacker.reaction_time = 48 h  @ai_tempo
        attacker.actor = "The human team"
```

- The thing's text is the reader-facing text of the operation; the brief shows it under "The AI
  operation".
- The AI's access is a named state: of the attacker, such as `access` above, or of another thing
  that holds it. An example is the operators' remote-support account (`operators.remote`). The
  language does not check this.
- Its first move (the event `start`) and its events with `after` are the moves of the operation.
- Options set what the attacker holds at the start: a start state, such as `"Keeps hidden access"`.
  They also set who it is: `"Human team"` sets the human pace and the `actor` text that the event
  cards read.
- Every run has every event. A move that only some runs make sits in an event that cannot happen in
  the others. For example, its `when` needs hidden access, which the attacker does not hold in those
  runs.
- With `sees`, the attacker is an actor ([language.md §2.7](../../docs/language.md#27-actors)): its
  decisions, the events with several outcomes, read only what it sees, and a reader or an agent can
  pick their outcomes in place of the model ([engine.md](../../docs/engine.md#play)).

The language and the build check nothing that is specific to an AI operation. The attacker is a
thing like any other. Its inputs, states and events are ordinary parts, and the build checks them
as it checks every part. The build reads no `role`. Only the pages read the thing as the AI
operation (`tools/publish/pages.py`). Its moves are its first move and its events
with `after`. Its pace is the input that one of its events waits (`after reaction_time`) and that a
run's other options set, such as `"Human team"`. The attacker's texts name the attacker in braces
(`{actor}`). Its value, "The AI", starts with a capital letter, so the braces start a sentence. In a
run whose options give that text another value, the cards show the human team as the actor. The
pace does not decide who acts: an option can change the AI's pace and keep the AI.

## The executable AI layer

The start is the event `start` of the attacker, at hour zero. In an incident its lines make the
first change, which opens the incident. In an operation it has no lines and only starts the clock:
the attacker's events time their moves from it (`since(attacker.start)`)
([events](../../docs/language.md#26-events)). After that, the AI reacts to what the defenders do:

- **Trigger.** An event of the attacker with `after` triggers at a defender step that the attacker
  can observe. Its `when` reads a defender event or condition that the attacker sees, such as
  `count(operators.find) > 0`.
- **Reaction delay.** The event waits for the attacker's reaction time (`after reaction_time`). This
  is the time from the moment that the attacker sees the defenders' step until it acts.
- **Cancellation.** The event's outcomes read the state of the AI's access in their chances, as
  conditions. When the defenders contain that access while the event waits, the delay still ends,
  and the event takes `stopped` (the access is gone) or `skipped` (the step is moot) instead of
  `done`. So a defender who removes the attacker first stops it. Exact ties go to the defender: the
  defenders' things come before the attacker in the file, so at one moment their events fire first.
- **Change.** The lines of the `done` outcome are the case's own mechanism: more recovery work, a
  halted service, a re-opened outage. An AI reaction never adds people, stock or capacity.

The build checks the attacker's parts as it checks every part of a model: the lines of the file, and
each structure with every part of it, its bounds, domains and proofs
([python-api.md](../../docs/python-api.md#build-a-model)). It has no check of its own for the AI operation, or
for what the runs that compare with it change. Two questions stay with the author and the
reviewers. Does the attacker's reaction time slow only its reactions to the defenders' steps? Does
the removal of the attacker's access stop every reaction that still waits? They are questions 8 and
9 of the audit checklist in the [catalogue's conventions](conventions.md#the-audit-checklist), which
every new or rewritten scenario answers.

AI reactions are ordinary events with `after` and outcomes. So their moments, the event and its
outcomes `done`, `stopped` and `skipped`, are checked like those of every other event.

## Why AI rather than a human team

The scenarios are meant to be defensible, not bulletproof: every step should be plausible to a
reasonable domain expert, and every value rests on evidence or a stated assumption, but a skeptic can
always imagine a perfectly prepared human team that closes the gap. The comparison is with a realistic
human team instead, modelled on how human teams have actually operated.

- **What the AI adds.** Each case builds on AI capabilities that compound, backed by the AI evidence in
  the library (`AI-ORCHESTRATION-2026`, `AI-AGENT-TRUST-2026`):
  - a round-the-clock watch on the defenders' recovery, answering each step within minutes, cycle
    after cycle, until the defenders remove it;
  - many targets at once, each handled individually;
  - adaptation on the spot to the equipment, records or defences it meets;
  - specialist expertise on demand;
  - camouflage tailored to what the defenders expect, so recovery keeps failing without an alarm.
    Camouflage is bounded: defenders eventually suspect it or find it when they remove the attacker.
- **The realistic human team.** Documented teams struck at planned times and left or wiped systems
  (Ukraine 2015 and 2016), and their follow-ons came days later: two days passed between a state team's
  2022 grid outage and its follow-on (`E-MANDIANT22`). They did not sustain a round-the-clock reactive
  operation inside a defender's network for days. Moves that answer the defenders' recovery therefore
  run at a 48-hour human pace. Moves planned in advance, or timed to a predictable public event, run
  the same in both pathways. A human move that documented teams actually made in that situation stays
  in the human pathway: for example, in 2015 attackers switched breakers by hand through operators'
  screens (`E-CYOTE15-TIMING`).
- **Competent defenders.** Defenders who recognize tampering cut the attacker's channel and recheck at
  once, and fast containment still beats the AI. In most cases removing the attacker before it can act
  on the defenders' first recovery step is the decisive defender choice.

The shared assumption `A-AI-TEMPO` records the AI's machine pace and the human pace. No AI-run attack of
these kinds has been reported; the scenario, not the AI evidence, fixes the access and reach.

## The matched human pathway

`featured` in `brief.toml` names two runs: the AI run, then its comparison. The comparison names
the AI run with `versus`, and the pages check this
([catalogue.md](catalogue.md#the-brief-settings-brieftoml)). The rest is how the scenarios are written,
and the language does not check it. The comparison keeps the AI run's defender response and start
states. In most cases it adds only the `"Human team"` option, which sets the attacker's reaction
time to the human pace. In the example of the language page, `brief.toml` says
`featured = ["delayed_kept", "delayed_kept_human"]`, and the model says:

```text
runs:
    delayed_kept = "Delayed response" + "Keeps hidden access"
    delayed_kept_human = "Delayed response" + "Keeps hidden access" + "Human team" versus delayed_kept
        "Delayed response · Human team keeps hidden access"
```

Where the AI's edge is not its pace, the comparison takes another option, which changes the
attacker's conduct: an AI that obeys a stop order. The brief states what actually differs between the two runs. It reads the options of
the two runs. It names each option that the comparison takes in place of the AI run's, in its
heading and beside each key input whose value differs. The difference between the two runs is what
the AI adds under the same response. A case with one featured run has no comparison and no brief.

## What the AI's edge is measured on

Each case reports how much of the defenders' recovery the AI undoes: extra hours of outage, shortage or
degraded service, extra recovery work to redo, or how much faster containment must be to hold harm at
the human pathway's level. The outputs that `show` in `brief.toml` lists, other than deaths,
serious casualties and economic loss, are these measures. The brief compares them
first. Deaths, serious casualties and economic loss are reported alongside and move where the
mechanism moves them; they are an outcome of the model, never a design target. Where a case's deaths
barely move, its brief says so and the recovery measure carries the comparison. No mechanism is chosen
or tuned for the harm it produces.

## Outcome orders

A scenario file states no order of the outcomes across runs, because options are choices that users
combine. The orders that the standard runs must keep are acceptance tests, frozen in each scenario's
own tests: for example, that a better defender response never produces more deaths, or that the
human team never produces more harm than the AI. Along each tuple of runs, best to worst, no listed
outcome falls. The tests check the final values of each default study, and of the study under each
saved edit set in `scenarios/<ID>/edits/`, among the runs that the edit set edits alike: an edit to
one compared run, to its defender response or to its start states changes what is compared. A value
that is not estimated breaks an order; it is never treated as zero.

## Story and briefs

Only the `summary:` and the notes in `notes:` are written as prose. The summary opens the brief,
and its first sentence is the hook. In `notes:`, `counterfactual` says what a human team could
equally do, `decisive` names the decisive defender choice, and `limitations` keep the uncertainty and
evidence caveats (catalogue.md).
`python -m tools.publish` generates the rest of each brief in `scenarios/<ID>/results/brief.md` from
the scenario, its `brief.toml`, the library records behind the AI layer and the completed default
study. Each part of the brief comes from one place:

- the steps and timelines, from the texts of the events, of their outcomes and of the start;
- the compared runs, from `featured:`;
- who is harmed, from the outputs;
- the key inputs, from `drivers:`, or else from `controls:`, or else from the inputs that the
  options set;
- the measures, from `show:`;
- the AI operation, from the attacker's text.

Harm figures always come from the completed study, never from a text.

The brief and the methods page each list the limits of the results that the scenario's reviewers
state (`limitations` in `notes:`), after who is harmed and after the premises. Each limit shows
once on a page: a limit that the page already states word for word, for example in the summary or
the decisive choice, is not listed again.

A fresh reader, who sees only the brief and uses no tools, reviews each brief.

## Case-specific operations

Each scenario's README records its AI mechanism, matched human pathway, decisive defender control
and comparison measures. Its local tests own the expected orders and oracle inputs. The generated
[scenario catalogue](../README.md) gives the computed comparison across available cases.
