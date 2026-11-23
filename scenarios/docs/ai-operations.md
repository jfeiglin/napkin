# AI operations

This page tells how a model shows an AI agent or another attacker, and how the pages compare an AI
with a human team. The [language reference](../../docs/language/README.md) gives the rules of each
line that this page names. This page uses the terms of the language reference
([Terms](../../docs/language/README.md#terms)).

## An attacker is a set of fixed rules

- The language has no special part for an attacker or for an AI. An attacker is an entity, as a crew
  or a plant is an entity. The compiler checks its values, events and flows as it checks all the
  other parts.
- The model fixes the rules of the attacker before the run. Events, stages and triggers say what the
  attacker does and when. Inputs say how fast it acts, what it reaches and how it behaves. The options
  of a named run set these inputs.
- No part of a model observes the run and decides during it. A decision is a value that a stage
  stores and that a branch reads. [changes.md](../../docs/language/changes.md) lists the forms of the
  old language and what replaced them.
- A breakpoint lets you ask what happens when the attacker or a defender acts differently at one
  point. Stop the run there, and edit a value
  ([Ask a question at a breakpoint](#ask-a-question-at-a-breakpoint)).

## A worked example

In this example, an attacker changes the chlorine dosing of a treatment plant. The operators find
each change and reset the dosing. While the attacker keeps its access, it changes the dosing again
after each reset. The responders remove the access some time after the first find. The option of
the group "Attacker" sets the pace of the attacker. An AI agent comes back within minutes, and a
human team comes back about two days later.

The values and the evidence of the example are invented. The package is a folder `dosing_attack/`
with this `model.scn` and the `brief.toml` below.

```scn
scenario "Dosing attack and operator recovery"
    summary "An attacker changes the chlorine dosing of a plant. The operators find each change and reset the
        dosing. While the attacker keeps its access, it changes the dosing again after each reset."
    horizon 72 h
    scope "One hypothetical treatment plant and its operators. All values are illustrative."

plant: @exercise
    "A treatment plant whose chlorine dosing the attacker can change."
    title "Treatment plant"
    dosing: enum[NORMAL, TAMPERED] = NORMAL
        "Chlorine dosing"
    resets = 0 @exercise
        "Resets by the operators"
    tampered_hours: h = 0 h in [0 h,] scale 72 h @exercise
        "Hours with tampered dosing"
    flow count_hours: SOURCE -> this.tampered_hours @exercise
        request = formula(1 if this.dosing == TAMPERED else 0)

operators: @exercise
    "The plant operators and the responders who remove the attacker's access."
    input find_time = 2 h in [0.25 h, 48 h] @exercise
        "Time from a dosing change until the operators find it and reset it"
    input removal_time = 22 h in [1 h, 240 h] @exercise
        "Time from the first find until the responders remove the attacker's access"
    found: bool = false
        "The operators found a tampered dosing"
    reset_dosing = event(): @exercise
        "The operators find the tampered dosing and reset it."
        when plant.dosing == TAMPERED:
            this.reset_dosing.start()
        after this.find_time:
            this.found = true
            plant.dosing = NORMAL
            plant.resets += 1
    remove_access = event(): @exercise
        "The responders remove the attacker's access."
        when this.found:
            this.remove_access.start()
        after this.removal_time:
            attacker.access = false

attacker: @exercise
    "An attacker that keeps its access until the responders remove it."
    input return_time = 0.25 h in [0.05 h, 96 h] @exercise
        "Time from a reset until the attacker changes the dosing again"
    access: bool = false
        "The attacker holds access to the dosing controls"
    changes = 0 @exercise
        "Dosing changes by the attacker"
    first_move = event(): @exercise
        "The attacker changes the dosing through the plant's remote-support account."
        when t >= 0 h:
            this.first_move.start()
        after 0 h:
            this.access = true
            plant.dosing = TAMPERED
            this.changes += 1
    come_back = event(): @exercise
        "After a reset, the attacker changes the dosing again while it keeps its access."
        when plant.dosing == NORMAL and this.access:
            this.come_back.start()
        after this.return_time when this.access and plant.dosing == NORMAL:
            plant.dosing = TAMPERED
            this.changes += 1

options "Attacker":
    "AI agent":
        "An AI agent acts within minutes of each reset."
        attacker.return_time = 0.25 h @ai_pace
    "Human team":
        "A human team comes back about two days after a reset."
        attacker.return_time = 48 h @human_pace

options "Response":
    "Standard removal":
        "The responders remove the access 22 hours after the first find."
    "Early removal":
        "The responders remove the access 4 hours after the first find."
        operators.removal_time = 4 h @exercise

runs:
    ai_agent = "AI agent" + "Standard removal"
        "An AI agent against the standard removal"
    human_team = "Human team" + "Standard removal"
        "A human team against the standard removal"
    ai_agent_early = "AI agent" + "Early removal"
        "An AI agent against the early removal"

record exercise: assumption "Illustrative times and counts for a tabletop exercise."
record ai_pace: assumption "An AI agent watches the plant without a break and acts within minutes."
record human_pace: assumption "A human team plans each move and comes back about two days later."
```

| Part | Lines | What it does |
| --- | --- | --- |
| The first move | `first_move`, `when t >= 0 h:` | At 0 h, the attacker gets its access and changes the dosing. |
| The access | `access: bool` | A stored value of the attacker. Only the responders set it to `false`. |
| What the attacker knows | `when plant.dosing == NORMAL and this.access:` | The trigger reads the dosing, which the attacker controls, and its own access. It does not read a value of the operators. |
| The pace | `after this.return_time when …:` | The stage waits for the pace of the attacker. Its guard reads the access once, when the stage comes due. If the responders removed the access during the wait, the stage does nothing. |
| The defenders | `reset_dosing`, `remove_access` | The operators react to the tampered dosing. The clock of the responders starts at the first find, not at the attack. |
| Who attacks | `options "Attacker":` | "AI agent" sets the pace to 0.25 h. "Human team" sets it to 48 h. |

The three named runs give these values at 72 h:

| Named run | `plant.tampered_hours` | `plant.resets` | `attacker.changes` |
| --- | ---: | ---: | ---: |
| `ai_agent` | 22 h | 11 | 11 |
| `human_team` | 2 h | 1 | 1 |
| `ai_agent_early` | 6 h | 3 | 3 |

The AI agent comes back 15 minutes after each reset. Thus it changes the dosing 11 times before the
responders remove its access at 24 h. The human team would come back at 50 h, but its access goes at
24 h. Thus it changes the dosing once.

```sh
napkin run dosing_attack --run ai_agent --value plant.tampered_hours,plant.resets,attacker.changes,attacker.access --at 0h,24h,72h
```

```text
Dosing attack and operator recovery: the run ai_agent, a median run to 72 h
                                         unit   0 h    24 h    72 h
plant.tampered_hours (Treatment plant)   h      0      21.5    22
plant.resets (Treatment plant)                  0      10      11
attacker.changes                                1      11      11
attacker.access                                 true   false   false
```

## Compare an AI with a human team

A comparison of an AI with a human team is two named runs and one named comparison in `brief.toml`
([catalogue.md](catalogue.md#named-comparisons)). The model holds no comparison. The engine runs each
named run separately, and the brief page compares the two records.

1. Write the human team and the AI as two options of one group, for example `"Attacker"`.
2. Write two named runs that take the same options of the other groups. One run takes `"Human team"`
   and the other takes `"AI agent"`.
3. In `brief.toml`, add a `[[comparison]]` with the AI run in `run` and the human run in `against`.
   The change "run − baseline" is then what the AI adds.
4. To show this pair first, write `featured = ["human_team", "ai_agent"]`. The baseline comes first.
5. List in `show` the measures of what the AI adds, for example the hours of tampered dosing.
6. Run `python -B -m tools.publish --write --scenario PACKAGE`, and read `results/brief.md`.

```toml
show = ["plant.tampered_hours", "plant.resets", "attacker.changes"]
featured = ["human_team", "ai_agent"]

[[comparison]]
run = "ai_agent"
against = "human_team"

[[comparison]]
run = "ai_agent_early"
against = "ai_agent"
```

The brief page then starts with this table:

```text
## ai_agent against human_team

| Reading | Unit | human_team | ai_agent | Change (run − baseline) | Change (%) |
|---|---|---:|---:|---:|---:|
| plant.tampered_hours | h | 2 | 22 | 20 | 1000 |
| plant.resets | 1 | 1 | 11 | 10 | 1000 |
| attacker.changes | 1 | 1 | 11 | 10 | 1000 |
```

The second comparison shows the effect of an earlier removal against the same AI agent. To compare
the pace of an attacker under uncertain inputs, put both runs in one `[[spread]]`. The publisher then
pairs the samples of the two runs ([catalogue.md](catalogue.md#spreads-and-their-edit-documents)).

## Ask a question at a breakpoint

`napkin play` stops a run before an event, a stage or a statement. At the stop, you can read values
and edit a stored value. The edit is the action: the run goes on from the edited value. A run that
stops and goes on without an edit gives the same record as a run without a stop.

This session stops the AI run before the first return of the attacker, at 2.25 h. It removes the
access there, and the run goes on to 72 h:

```text
$ napkin play dosing_attack --run ai_agent --break 'attacker.come_back.step[0]' --value attacker.access,plant.tampered_hours,attacker.changes
Dosing attack and operator recovery: the run ai_agent, a median run to 72 h

Stop 1 at 2.25 h: before attacker.come_back.step[0] (stage at dosing_attack/model.scn:62), in attacker.come_back#0 of attacker.
Next: attacker.come_back.step[0] of attacker.come_back#0, from its start.
  attacker.access                          true   edit: true or false   The attacker holds access to the dosing controls
  plant.tampered_hours (Treatment plant)   2 h    edit: a number        Hours with tampered dosing
  attacker.changes                         1      edit: a number        Dosing changes by the attacker
Edit with PATH = VALUE, or: save FILE, go, quit.
> attacker.access = false
  attacker.access: true -> false
> go

The run ends at 72 h.
                                         unit   0 h    72 h
attacker.access                                 true   false
plant.tampered_hours (Treatment plant)   h      0      2
attacker.changes                                1      1
edit at 2.25 h, before attacker.come_back.step[0]: attacker.access true -> false
```

`save FILE` at a stop writes a checkpoint, and `napkin play MODEL --from FILE` goes on from it in a
new process. [cli.md](../../docs/cli.md) gives the commands.

## Rules for a model of an attack

Answer each question with yes, or change the model.

1. Does each event of a defender react to a value that its entity can see, and not to the attack
   itself?
2. Does the clock of each defender start when someone finds the problem, and not at the attack?
3. Does each event and flow of a defender read only what the defenders can see? It must not read a
   hidden value of the attacker, such as `attacker.access`.
4. Does each event of the attacker read only what the attacker can know?
5. Does the pace of the attacker delay only its reactions to the steps of the defenders?
6. When the defenders remove the access, does each stage of the attacker that still waits do
   nothing? Write the access in the guard of the stage (`after D when C:`).
7. Do the AI run and the human run differ only in the options of the attacker?
8. Does each reaction of the AI change only what the access of the attacker reaches? An AI reaction
   adds no people, no stock and no capacity.

## Disruptions in the catalogue today

No model of the catalogue has an entity for an attacker today. The packages receive their
disruptions as inputs and options, with fixed rules:

| Package | Entity | Rules | Groups of options |
| --- | --- | --- | --- |
| `heat_wave_blackout` | `incident` | A supplied safety hold. Inspection reports on a calendar (`FIXED`) or after the crews clear their work (`AFTER_CLEARANCE`). With `acknowledge_stop`, the reports stop at detection. Without it, they arrive until containment. | "Inspection schedule", "Inspection response", "Stop order" |
| `water_controls_wipe` | `support` | Batches of regional support requests at a fixed interval, or after the backlog of the office clears (`linked`). Containment filters the later batches. | "Regional support workload" |
| `iv_fluid_shortage` | `quality_review` | Quality notices at a fixed interval, or after the review of the last notice | "Quality documentation", "Documentation staffing" |
| `cyber_learning_loop` | No entity | No disruption. The options set the path of AI progress. | "AI progress" |

The option "Acknowledge the stop order" of `heat_wave_blackout` sets a rule of conduct with one input.
It changes when the reports stop, and it keeps the response of the defenders the same. The example
[incident_response_tempo](../../examples/incident_response_tempo/README.md) has an entity `attack`
whose attempts come at a fixed interval or after recovery. [deviations.md](deviations.md) tells how
each package differs from the earlier catalogue.
