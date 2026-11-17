# The catalogue's conventions

Each case of the catalogue follows one attack from its first move, through the defenders' response,
to its consequences. The [modelling guide](../../docs/modeling-guide.md) says how to model with napkin
on any subject. This page adds the conventions that the catalogue's models follow for the attacker
and the defenders. The compiler reads none of them. The authors and the reviewers check them, and
the pages read some of them ([catalogue.md](catalogue.md)). [AI operations](ai-operations.md) says
how the AI's own behaviour runs, and how each case compares it with a human team.

## Start a package

1. Run `python -B -m tools.new PACKAGE --title "…"`. It makes the folder `scenarios/PACKAGE/` with
   each file of a package in its shape and no content, and prints the list of what to write, in
   order.
2. Write the model part by part. After each part, run `napkin run scenarios/PACKAGE`: it gives the
   file, line and column of each diagnostic, or each run's outcomes at the end (`--run NAME` for one
   run, `--events` for its events, `--set NAME=VALUE` for an edit). The run store keeps each run, so
   only the runs that a change touches run again.
3. When the model runs, write the summaries with
   `python -B -m tools.publish --write --scenario PACKAGE`.
4. Run `python -B -m tools.check --scenario PACKAGE` until it passes.

Write each text that a reader sees to the writing style
([CONTRIBUTING.md](../../CONTRIBUTING.md#writing-style)). That includes each text of a thing, a
template, an event, an outcome, a flow or an output, and each label of a value. It also includes the
status lines, the menu lines of the options and the texts of the runs.

## One attack on several places

When one attack reaches several places that share most of their model, make them one package with a
variant for each place (the guide, section 11).

- Put what the places share in the main file and its modules: the templates, the attacker, the
  response, the outputs, the options and their records.
- Give each place its variant, `scenarios/<package>/variants/<place>/model.scn`, with the summary
  and the scope of that place, its things and their records.
- In the module, put the defenders' things before the attacker's, so that their events go first at
  one moment. A variant's lines come after its main file's, so keep the main file free of things
  when the order of the lines matters.

`water_controls_wipe` is such a package: its module `water.scn` holds the mechanism, and each of its
16 variants holds the water systems, the homes and the hospitals of one place.

## The attacker

- The attacker is the one thing with `role adversary`. The pages show it as the AI operation, and
  they reject a second thing with that role.
- The attacker's first move is its event `start`, `event start when t >= 0 h:`. Its records cite the
  incidents and the techniques, and the premise `START` of the notes states the limits of what they
  show ([capabilities.md](capabilities.md)).
- What the attacker still holds is a state, not a thing of its own. `iv_fluid_shortage` gives the
  attacker `var access: "none" | "kept" = "none"`. `water_controls_wipe` gives it to the system that
  holds the credential: `platform.access`.
- Each event of the attacker reads only what the attacker could know, and the record on its line
  says how it knows: for example, the attacker sees moves start through the data records that it is
  inside.
- The attacker's reaction time slows only its reactions to the defenders' steps.
- When the defenders remove the attacker's access, each event of the attacker that still waits
  ends as `stopped` (the access is gone) or `skipped` (the step is moot), not as `done`.

## The defenders

- Each defender's event reacts to a consequence that its thing can see, not to the attack. The crews
  react to the outage, not to the attacker's command.
- A defender's clock starts when someone finds the problem, not at the attack. Defenders cannot start
  to remove an attacker that no one has found.
- A defender's event or flow that reads the attacker's hidden state is a fault of the model. Fix it:
  the event or the flow reacts to what its thing can see.
- The defenders' things come before the attacker in the file. So at one moment their events fire
  first, and exact ties go to the defender. A comment says why.

## Options and runs

- The options differ in what the world holds at the start, in input values and in texts, not in how
  the defenders work.
- The group "Response" holds the defenders' tiers. Every run names one of them, and they set inputs
  only. The line `choice_group = "Response"` of `brief.toml` tells the pages that its options are the
  responses ([catalogue.md](catalogue.md)).
- An option with no lines means "the defaults". Where a run names no option of a group, the pages
  show the group's first option that has no lines.
- Name each other group for what its options are, because the pages name the options by their group:
  Access, Attacker and Reach in `water_controls_wipe`, "AI conduct and protection" in
  `heat_wave_blackout`.
- The matched comparison of an AI run says `versus` the AI run. The human team's run is the same run
  with the option "Human team": in `water_controls_wipe`, `delayed_kept_human` says
  `versus delayed_kept`. `cyber_learning_loop` compares its AI runs with `no_ai`, which keeps every
  driver at its value today.
- A run's text names the defender response, then the attack, joined by " · ": "Delayed response ·
  Human team keeps hidden access".
- `featured` in `brief.toml` names a run and its matched comparison. The pages reject
  `featured = ["r", "c"]` unless `c` says `versus r`.

## Outputs and the brief

- Each output says whom it covers: the catalogue's check requires a scope ([catalogue.md](catalogue.md)).
- The headline outputs have the categories `deaths`, `casualties` and `loss`, or `unestimated` with
  the reason. Each output of the category `casualties` cites the convention `HAZUS-SEVERITY` of the
  library.
- The brief compares the two featured runs first on two measures: the first two outputs of `show`
  that have no category and that count a total over the run. Then it compares them on the harms. So
  list the measures of the AI's edge first among those outputs.
- Name the inputs that the story turns on in `drivers` (`brief.toml`).

## The parts of the files

| Part | Use it for |
| --- | --- |
| `notes:` | What the authors and the reviewers concluded: the premises, the limitations, the verification, the reachability, the benchmark, and the two optional texts of the brief (`counterfactual`, `decisive`), with the keys that [catalogue.md](catalogue.md) gives. The calculation never reads them |
| `brief.toml` | What the briefs show first (`show`, `drivers`, `featured`), the name of the attack (`attack`), the group of responses (`choice_group`), the sweeps of the run table and the spreads. The calculation never reads it |
| `style.toml` | How `napkin draw` pictures the model ([draw.md](../../docs/draw.md)). The calculation never reads it |
| `evidence/` | The sources, the claims and the assumptions. Only `tools.evidence.integrate` writes the claims and the sources ([evidence/README.md](evidence/README.md)) |

## Change a model of the catalogue

`python -B -m tools.compare` does steps 1 and 3 of the guide's section 14. It records the results of
the base revision and of the working tree for each scenario, and prints every difference bit for bit
([CONTRIBUTING.md](../../CONTRIBUTING.md#testing)).

## The audit checklist

Every new or rewritten case answers the guide's checklist (its section 15) and these questions. Answer
each one with yes, or change the model.

1. Does each defender's event react to a consequence that its thing can see, and not to the attack
   itself?
2. Does each defender's clock start when someone finds the problem, and not at the attack?
3. Does each defender's event and flow read only what the defenders can see, and never the
   attacker's hidden state?
4. Do the defenders' things come before the attacker in the file?
5. Do the options differ only in start states, input values and texts, and not in how the defenders
   work?
6. Does every run name one option of the group "Response"?
7. Does each run of the human team say `versus` the AI run that it matches?
8. Does the attacker's reaction time slow only its reactions to the defenders' steps?
9. Does removing the attacker's access stop every event of the attacker that still waits?
