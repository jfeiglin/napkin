# The picture of a model

`napkin draw` draws a static picture of a model as one SVG file. The picture shows each thing of
the model, its stocks, its flows and its state machines, and what each thing reads, changes and
moves of the others. It is a check of the model: when an arrow surprises a reader, the model is
wrong. The optional file `style.toml` of a package places, groups and hides the things, labels the
groups, gives the icons and says where each state machine goes. No run reads it.

## Contents

1. [An example](#1-an-example)
2. [What the picture shows](#2-what-the-picture-shows)
3. [How the layout works](#3-how-the-layout-works)
4. [The command](#4-the-command)
5. [style.toml](#5-styletoml)

## 1. An example

```text
$ napkin draw examples/reservoir -o docs/draw-example.svg
docs/draw-example.svg: 2 things, 2 arrows
```

![The picture of the example examples/reservoir: the operator and the reservoir](draw-example.svg)

The model of `examples/reservoir/model.scn` has two things. Its `style.toml` places them, gives the
reservoir an icon, shows the operator's rule, and turns on the panels of the reservoir's equations:

- **The reservoir** has the icon `drop`. Its stock, the water in the reservoir, is the blue row. The
  storm fills it: the teal pipe comes from outside the model, the small circle. Its two tallies are
  the yellow rows: the water let out over the spillway, and the time with the water above the risk
  level. The flows into the tallies are in the tooltips of their rows. Each row carries its symbol,
  `W`, `S` and `T`, as the equations write it.
- **The spillway** is a named state of the reservoir, so its state machine is in the card. The
  green dot marks the state at the start, `closed`. Transition 1 goes from any state to `open`: the
  event `decide` of the operator, which reads nothing of the spillway.
- **The operator** has the role `operator`, so its card has the icon `server`. The diamond says
  that it decides: its event `decide` is a choice that a person can play
  ([language.md §2.7](language.md#27-actors)). The row under its title gives the rule of `decide`
  in words: when it happens, the choice, and what each outcome changes.
- **The arrows.** The grey dotted arrow goes from the reservoir to the operator: the operator reads
  the water level. The red dashed arrow goes from the operator to the reservoir: the operator
  changes the spillway.
- **The panels** under the legend give the reservoir's equations, a table of their symbols with
  each value, unit and chosen range, and the references of the numbers on them. Each number is a
  record of the model: here, most are assumptions of the example.

## 2. What the picture shows

The picture has a title (the scenario's title), a subtitle, the cards, the arrows between them, the
frames of the groups and a legend. Each part has a tooltip: in a browser, point to a part to see its
name in the model and its details. The picture does not need the tooltips: what a stylesheet turns
on shows in the picture itself, also as an image on a page or in a PDF.

**The subtitle** names the model and its run. With `--run`, it gives the run's name and label, the
options when the label does not name them, and the run that it is compared with (`versus`).
Without `--run`, it says "all n runs" when the picture joins several runs. It also says how long a
run lasts. It names, by their titles, the things and templates that `[layout] hide` leaves out ("not
drawn: …"). A second line holds what does not fit on the first.

**Cards.** Each thing is a card: a thing made without a template, an instance of a template, or
the copies of one line (`name: Template * k`), which share one card with a badge `×k`. A card shows
the thing's title, on two lines at most, and its icon. An actor with a choice
([language.md §2.7](language.md#27-actors)) has a diamond. The card of the thing that makes the start
event has a green ▶: its event `start` begins each run. The tooltip of a card names the file that
writes the thing, and lists the card's connections: for each kind of arrow, the cards that it
reads, follows, changes, fires or moves, and the cards that do it to the card.

**Stocks, tallies and flows.** A card shows its stocks as blue rows and its tallies as yellow rows
with a gauge ([language.md §2.4](language.md#24-fields)). It shows four of them at most
(`[layout] stocks`): the stocks first, then those with more pipes, or the rows that `[stocks]`
names, in its order. A row "+n" stands for the others, and its tooltip names them. A flow between
two stock rows of the card, or between a stock row and the outside of the model, is a teal pipe with
a valve. The flows between the same two ends are one pipe, which shows their number; its tooltip
gives their labels. A flow into a tally, or into a stock that is not shown, is in the tooltip of its
row. A flow to or from another card is an arrow of the kind "moves".

**State machines.** Each named state (`var s: "a" | "b" = "a"`) is a small state machine: a pill
for each state, and a green dot on the state at the start. Each event that sets the state is a
purple transition. It starts from the states in which the event can happen, or from "any state"
when the event's condition does not limit them. A number on each transition names it in the key
under the machine: the events and the things that make them. When an option sets the start of the
state, the key says so: "Options set the start: …", with the option and the state. A machine with at
most 4 states and 6 transitions is inside its card; a larger machine is beside the card, below it in
the same column. `[state]` in `style.toml` can put a machine beside its card or hide it.

**Events.** `[triggers]` can show what makes the events of a card happen, at the bottom of the card,
in plain words that come from the model ([`[triggers]`](#triggers-the-events-of-a-card)). For
example, a row "**strike again** — when watch is preparing, access is kept, and reaction time has
passed since controls back". The words are the names of the event and of the values that its
condition reads: better names in the model give better rows. A row that does not fit ends with "…".
The card's tooltip then holds each event's full line, its text and its condition as the file writes
it. No card shows its events without `[triggers]`.

**Arrows.** One arrow joins two cards for each kind of link between their parts. A part is an event
(its condition, its delay, the chances of its outcomes and their lines), a flow, a formula, the
start value or the bounds of a number, an option's start value, a status or a share. Outputs and
checks are not parts: nothing in a run reads them.

| Kind | What a part of one card does | The head of the arrow is at | Drawn as |
| --- | --- | --- | --- |
| Reads | It reads a value of the other card | The card that reads | A grey dotted line, an open head |
| Follows | It reads when an event of the other card happened (`since`, `count`) | The card that reads | A purple dashed line, an open circle |
| Changes | It sets, adds to or takes from a value of the other card, or shares out its flow | The card whose value changes | A red dashed line, a filled head |
| Fires | A line of its event makes an event of the other card happen | The card whose event happens | An orange dash-dot line, a head with a bar |
| Moves | It moves material into or out of a stock of the other card, with a flow or a `move` | The card whose stock changes | A thick blue line, a filled head |

Each two kinds differ in their width, their dashes or their head, so they differ without colour too.
The tooltip of an arrow names the values that it stands for, and for "changes" the words of its
lines (sets, adds, takes, shares).

- **Light and hidden.** `[arrows]` gives each kind a look: full, light or hidden. A light arrow is
  paler and thinner; its colour is its kind's colour mixed with the paper. A hidden kind draws no
  arrow, and the legend says "not drawn"; the cards' tooltips still list its connections. Without
  `[arrows]`, reads and follows are light and the other kinds are full.
- **Bundles.** The arrows of one kind from one card toward one side share one line, the trunk, and
  branch near the cards at their ends. A small dot marks each branch. The tooltip of a trunk names
  the cards that it reaches. Without `[arrows] bundle`, the reads and the follows bundle.
- **Pointing at a card.** In a browser that knows the CSS selector `:has()` (Chrome 105, Safari
  15.4, Firefox 121), the arrows of a card stand out and the others fade when a reader points at the
  card. The SVG has no script for this, and a picture shown as an image does not do it.

**Equations, symbols and references.** `[equations]` puts panels under the legend
([`[equations]`](#equations-the-equations-of-a-card)), for the things that it names. When the picture
is wide enough for two panels side by side, the Equations go on the left and the other panels on the
right. Else they go one under another.

- **Equations.** For each thing, the balance of each stock (dS/dt = what flows in − what flows out),
  the rate of each flow, and the formulas that the rates read, as many hops deep as `depth` says.
  Other lines say what changes the run. They give the bounds of a stock, the flows that share a
  stock and the flows that move together. They give the events that change a value at once
  (`C ← C + ρ·L  at strike again`). The math comes from the model's own expressions, so it never
  disagrees with the model. A yes/no formula is written with ⇔ (`h ⇔ a > 1 ∧ b`): it holds exactly
  when its right side holds. A line that does not fit ends with "… (continues in the LaTeX)". Each line keeps its LaTeX in an attribute
  `data-latex`, and `napkin draw --latex FILE` writes all of it to a file.
- **Symbols.** Each symbol of the lines, with what it means, its unit, its value (with the values that
  options give), and, for an input, its chosen range and its distribution. A start that a formula
  sets shows as math with the symbols (`n · δ · χ`), and each value that it reads has a row too. In a
  table too narrow for the math, the start shows as the file writes it. A chosen range is the
  range that a reader can set; it is not a measured interval, and a note under the table says so.
  Each shown stock row of a card that has a block of equations carries its symbol as a small tag.
- **References.** With `[references] show`, each line and each input carries small numbers, and a
  numbered list says where they come from. Each entry starts with its kind: a source, a source
  applied here, an identity, a convention, or an assumption, with its review status (for example
  "Assumption, not reviewed"). The colour of a number shows its kind too: a source blue, a source
  applied here teal, an identity or a convention grey, an assumption amber. A source's entry names
  its author, year and title, the places in it that the model uses, and a link to it. A value that the
  model works out from others has no number: its equation leads to the numbered inputs. A start
  that the file writes as a value has the numbers of its records. The line of a formula carries
  the numbers of the record of its form. No entry shows a record's ID.

**The legend** shows only the marks that the picture draws, and the kinds that it hides: "Reads a
value", "Follows an event", "Changes a value", "Fires an event", "Moves material", "Stock", "Tally",
"Flow", "State", "Event that changes the state" and "Decides". A hidden kind's item ends with "not
drawn".

**Icons.** A card has the icon that `[icon]` gives it, else the icon of its role, else none
([`[icon]`](#icon-the-icons)). A card without an icon keeps the place of the icon free.

**Light and dark.** The SVG file has no script, no external font and no image. Its colours are CSS
custom properties, and a `prefers-color-scheme: dark` rule changes them: the picture follows the
light or dark theme of the page that shows it. Each element also has its light colour as an
attribute, for a reader that does not know CSS custom properties.

## 3. How the layout works

The layout is the same for the same model, picture and run: the same input gives the same bytes.

1. **Placements and groups first.** A card that `[place]` places takes its column. A row orders it
   among the cards of its column. The members of a group are one block in each column, and the
   blocks go in the order of `[group]`.
2. **Layers.** The other cards take their columns from the drawn arrows of the kinds "changes",
   "fires" and "moves" (a hidden kind counts for nothing). Each card goes in the column after the latest card that changes it, fires its events
   or moves its material. A cycle of arrows is broken first. A card with only "reads" and "follows"
   arrows takes the middle column of the cards that it reads or that read it, and a card with no
   arrow takes the last column. A column with no card takes no room, and a column holds 8 cards at
   most (`[layout] cards_per_column`): a fuller column splits into the fewest columns that hold it.
3. **Fewer crossings.** Sweeps over the columns order the cards of each column by the positions of
   the cards that they join. Of 24 sweeps, the order with the fewest crossings of arrows wins. The
   shared line of a bundle counts once.
4. **Orthogonal arrows.** An arrow goes horizontally from its card, vertically on a track in the gap
   between two columns, and horizontally to the other card. An arrow that passes a column goes
   through a gap of its own in that column; a bundle has one gap in each column that it passes, and
   one track in each gap of its trunk. The tracks of a gap are as few as the arrows that cross one
   height need, and each gap is as wide as its tracks need.
5. **Groups.** A group is a frame with its label around its members only. The other cards of its
   columns go above or below it.

## 4. The command

```text
napkin draw [--variant NAME] [--run NAME] [--style FILE] [-o FILE] [--latex FILE] [TARGET]
```

| Flag | What it does |
| --- | --- |
| `--variant NAME` | Draw this variant of the package. A package with several variants needs it: without it, `napkin draw` lists the variants and stops |
| `--run NAME` | Draw this run. The picture leaves out the parts that cannot act in the run, such as an event whose condition never holds with the run's start values, and their arrows. The texts of the run's options fill the labels |
| `--style FILE` | Use this file in place of `style.toml` |
| `-o FILE` | Write the SVG to this file. Without it, the file is `<package>[.<variant>][.<run>].svg` in the current folder |
| `--latex FILE` | Also write the equations, the symbols and the references of `[equations]` to this file, as a LaTeX fragment. It needs the packages `amsmath`, `longtable` and `hyperref`, in this order. A long block of equations and the table of symbols break across pages |

Without `--run`, the picture of a model with one run is the picture of that run. The picture of a
model with several runs joins their pictures: it draws each part that can act in one run or more.

The LaTeX fragment of `--latex` has the same equations, symbols, ranges and references as the
picture. Each block of equations is an `align*` in a group with `\allowdisplaybreaks[1]`. A page
can break between its lines, and the document keeps its own setting outside the group. The symbols
are a `longtable`, which repeats its header row on each page. A range has the words of the picture:
"chosen range lo–hi" or "range lo–hi". [cli.md](cli.md) gives the parts of the fragment.

```text
$ napkin draw scenarios/water_controls_wipe --variant juneau --run delayed_none
note: checked for run delayed_none only; `napkin compile` checks every run
water_controls_wipe.juneau.delayed_none.svg: 10 things, 25 arrows
```

With `--run`, `napkin draw` checks the model for that run only, as `napkin run` does. `napkin
compile` checks every run.

A picture taller than a PDF page holds (19,200 px) gets a note. Show fewer things in `[equations]
things`, or use `--latex` for the equations.

The command, its flags and its exit codes are on [cli.md](cli.md).

## 5. style.toml

`style.toml` is an optional TOML file. It changes only the picture: no run reads it, and the model
hash does not cover it, so a change to it keeps every result and every saved edit. Its tables are
`[layout]`, `[place]`, `[group]`, `[icon]`, `[state.<thing>]`, `[stocks]`, `[arrows]`, `[triggers]`,
`[equations]`, `[references]`, `[symbol.<thing>]` and `[subscript]`. Each table is optional, and so
is each key of a table.

A name in the file is a thing or a template. A thing is one of these: a thing made without a
template, an instance, or a set of copies by the name of its line (`waves` for `waves: Wave * 3`). A
template stands for each of its instances. A thing's own setting wins over its template's.

An example, for the variant `water_controls_wipe:juneau`:

```toml
[layout]
direction = "left-to-right"
hide = ["parts"]                         # things and templates that the picture leaves out

[place]                                  # anything that no line places lays itself out
attacker = { column = 1 }
platform = { column = 2 }
CrewPool = { column = 4, row = 2 }       # its instances take rows 2 and 3

[group]
"Repair crews" = ["CrewPool"]            # a labelled frame around these things only

[icon]                                   # one of the 20 icons; default: the role's icon, else none
drop   = ["Utility", "relief"]
wrench = ["CrewPool"]
house  = ["Households"]

[state.platform]
access = "beside"                        # inside | beside | hidden
```

### Where the file is

`napkin draw` and `napkin compile` take the first file of this list:

1. the file that `--style FILE` names (`napkin draw` only);
2. `style.toml` in the folder of the variant, for a variant;
3. `style.toml` in the folder of the package.

The file that they find is the whole picture: a variant's own file replaces its package's, and the
two never merge. Without a file, nothing is hidden, placed or grouped, and each card has the icon of
its role.

### `[layout]`

| Key | What it gives | Without it |
| --- | --- | --- |
| `direction` | The direction of the picture. Its one value is `"left-to-right"` | `"left-to-right"` |
| `hide` | The things and templates that the picture leaves out, with their arrows and transitions. A template hides each of its instances, and an instance hides only itself. The subtitle names them | Nothing hidden |
| `stocks` | The most stock and tally rows of a card before its "+n" row, a whole number from 1 to 8 | 4 |
| `cards_per_column` | The most cards of a column, a whole number from 2 to 16. A fuller column splits into the fewest columns that hold it | 8 |
| `card_width` | The least width of a card in px, a whole number from 170 to 400. A card whose title, rows or machines need more is wider, and the cards of a column are as wide as the widest | 170 |

### `[place]`

`name = { column = c, row = r }` places a thing or a template. `column` counts from 1 and is
required. `row` counts from 1, in the column, and is optional. Each is a whole number of 1 or more.

- A placed card takes its column. A column with no card takes no room, so `column = 4` stands next
  to column 2 when no card is in column 3.
- A row orders a card among the cards of its column. Two cards never have one column and one row.
- A template with a row places its instances on that row and on the rows that follow it, in the
  order of the model file. An instance with a place of its own takes that place.

### `[group]`

`"Label" = [name, …]` draws a frame with its label around these things and no other thing. A thing
is in one group at most.

- A row that would put a card inside the frame of a group that it is not in moves the card to the
  nearer end of the group.
- `napkin compile` refuses the rows that cannot hold, with exit 1:
  - a thing with a row between the rows of two things of a group that it is not in, in one column;
  - a thing of a group with a row above the row of a thing of an earlier group, in one column: the
    frames go down in the order of `[group]`.

For example, a `style.toml` of juneau puts `controls_crew` on row 1 and `field_crew` on row 3 of
column 3, in the group "Repair crews", and `responders` on row 2 of the same column:

```text
$ napkin compile scenarios/water_controls_wipe --variant juneau
…
scenarios/water_controls_wipe/variants/juneau/style.toml: error: place.responders: puts responders in column 3, row 2, between controls_crew and field_crew of group.Repair crews: the frame of a group holds only its own things
```

### `[icon]`: the icons

`icon = [name, …]` gives these things and templates the icon. A name has one icon at most. An
instance's own icon wins over its template's, and the template's over its role's. A thing that no
line names has the icon of its role, from the table; a thing with another role, or with no role,
has no icon.

| Icon | For | The icon of the role |
| --- | --- | --- |
| `target` | An attacker | `adversary` |
| `server` | Computer systems and services | `operator` |
| `shield` | Responders and defenders | `responder` |
| `hospital` | Hospitals, clinics and care | `clinician` |
| `people` | People and teams | `community` |
| `gauge` | Controls and conditions | `environment` |
| `factory` | Plants and makers | |
| `tank` | Stores of a liquid or a gas | |
| `pipe` | Pipelines | |
| `bolt` | Electric power | |
| `drop` | Water | |
| `wrench` | Repair crews | |
| `truck` | Transport and deliveries | |
| `box` | Stocks of goods and parts | |
| `document` | Records, claims and changes | |
| `money` | Payments and the economy | |
| `house` | Homes and buildings | |
| `shop` | Shops and businesses | |
| `sun` | Weather and heat | |
| `alert` | Hazards | |

### `[state.<thing>]`

`[state.platform]` with `access = "beside"` says where the state machine of the named state
`platform.access` goes. The table names a thing or a template that the picture draws, and each key
is one of its named states.

| Value | Where the machine goes |
| --- | --- |
| `"inside"` | In its card, when it has at most 4 states and 6 transitions; else beside the card. This is the default |
| `"beside"` | Beside its card, below it in the same column, joined to it by a dotted line |
| `"hidden"` | Nowhere: the picture does not draw it |

### `[stocks]`

`supply = ["water", "reserve"]` gives the stock and tally rows of the card of `supply`, in this order.
The card shows the first rows of the list, at most `[layout] stocks`, and the "+n" row stands for the
others. The stock rows stay above the tally rows. A template's list goes to each of its instances,
and an instance's own list replaces its template's.

### `[arrows]`

| Key | What it gives | Without it |
| --- | --- | --- |
| `reads`, `follows`, `changes`, `fires`, `moves` | The look of the arrows of that kind: `"full"`, `"light"` (paler and thinner) or `"hidden"` (no arrow; the legend says "not drawn", and the cards' tooltips still list the links) | `"light"` for reads and follows, `"full"` for the others |
| `bundle` | The kinds whose arrows from one card toward one side share one trunk, as a list such as `["reads", "follows"]`. An empty list bundles nothing | `["reads", "follows"]` |

The file has no key for one pair of cards: a look is for a kind. A hidden kind places no card: only
the arrows that the picture draws decide the columns, so hiding a kind can move cards.

### `[triggers]`: the events of a card

Each level is a list of things and templates. A card shows the events of its thing at its level. A
thing's own level wins over its template's, and a name is in one level at most.

| Key | What the card shows | Without it |
| --- | --- | --- |
| `count` | One row: "n events" | — |
| `names` | A row for the name of each event | — |
| `rules` | For each event, its name and then its condition, its timing, its chance, what it changes and the options that switch it, cut by words to `lines` rows. The card is at least 280 px wide | — |
| `hover` | Nothing: only the card's tooltip holds the events | — |
| `lines` | The most rows of one event at `rules`, a whole number from 1 to 4 | 2 |
| `events` | The most events with a row, a whole number from 1 to 20; a row "+n more" stands for the others | 6 |
| `options` | Whether the lines name the options that switch an event on or off: true or false | true |

At every level, the tooltip of the card holds each event's full line, its text and its condition as
the file writes it. The words come from the model: the names of the event and of the values that
its condition reads, the units as written, and a few words such as "when", "has passed since" and
"is at most". `[triggers]` only shows events. To switch an event on or off in a run, the model uses
its options and runs.

### `[equations]`: the equations of a card

| Key | What it gives | Without it |
| --- | --- | --- |
| `things` | The things and templates whose equations the panels show. A template stands for its instances. Each thing makes the picture taller: name the 1 to 3 things whose stocks carry the story. `napkin draw` gives a note when a picture is taller than a PDF page holds (19,200 px) | No panels |
| `depth` | How many hops of formulas the lines follow from the rates, a whole number from 0 to 5 | 1 |
| `width` | The width of the panels in px, a whole number from 320 to 2400 | 720 |
| `lines` | The most rows of one equation, a whole number from 1 to 8 | 3 |
| `tags` | Whether each shown stock row of a card that has a block of equations carries its symbol: true or false | true |
| `symbols` | Whether the Symbols table shows: true or false | true |
| `checks` | Whether the lines show the `assert` checks of the things: true or false | false |
| `instances` | `"together"`: the instances of a template whose equations are the same share one block; `"each"`: each instance has its own | `"together"` |

### `[references]`

| Key | What it gives | Without it |
| --- | --- | --- |
| `show` | Whether the numbers and the References list show: true or false. It needs `[equations] things`, because the numbers go on its lines and symbols | false |
| `kinds` | The kinds of entry that the list holds, from `"source"`, `"source_transfer"`, `"identity"`, `"convention"` and `"assumption"`. The list always keeps `"assumption"`: a value that rests on an assumption shows it. When the list leaves out a kind that the shown values rest on, a line under its heading says so ("Not listed: sources.") | Every kind |

### `[symbol.<thing>]` and `[subscript]`

The equations of the picture write each value, flow and event with a short symbol, such as `W_s`.
The picture makes each symbol from the model's names, and a stylesheet can set one, for example to
use the symbols of a paper:

```toml
[symbol.supply]
water = "W_s"        # a value, a flow or an event of supply, exactly as written
drain = "delta_d"    # a Greek letter by its name, with a subscript of its own

[symbol.Utility]
stored = "S"         # a template's symbol: each instance adds its own subscript (S_jun, S_cm)

[subscript]
supply = "s"         # the subscript of the card of supply in the symbols that the picture makes
```

A symbol is a letter or a Greek name (such as `delta`), an optional `'`, and an optional `_` with a
subscript of letters, digits and commas, 12 characters at most. A thing's symbol is used exactly as
written: write `W_s` for W with supply's subscript, because a bare `W` has none. A template's symbol
has no subscript: each instance adds its own. An instance's own symbol wins over its template's. Two
values never have one symbol, and two cards never have one subscript. `[subscript]` names things, not
templates; a subscript is letters and digits, 10 characters at most.

### What `napkin compile` checks

`napkin compile` reads and checks the `style.toml` of each model that it compiles, and `napkin draw`
checks the file that it uses. A problem stops both, with exit 1. Each problem names the file and
the key, and the line for a file that is not TOML. The checks:

- Each table and each key is one that this version reads, so a misspelt key shows.
- `direction` is `"left-to-right"`; a column and a row are whole numbers of 1 or more; a place has a
  column; each icon is one of the 20; each place of a state machine is `inside`, `beside` or
  `hidden`.
- Each name is a thing or a template of the model. `hide` can name any of them. `[place]`,
  `[group]`, `[icon]` and `[state]` name only things that the picture draws: not a hidden thing,
  and not a template without an instance.
- A list names each thing once, a thing has one icon and one group at most, and two things never
  have one column and one row.
- The rows hold with the groups (see [`[group]`](#group)).
- Each key of `[state.<thing>]` is a named state of each thing that the name stands for.
- Each number of `[layout]` and `[triggers]` is a whole number in its range; each look of `[arrows]`
  is `full`, `light` or `hidden`; `bundle` names kinds of arrows; `options` is true or false.
- Each list of `[stocks]` names stocks and tallies of each thing that the name stands for; each name
  of `[triggers]` has an event; each member of `[symbol.<thing>]` is a value, a flow or an event of
  it, and each symbol and subscript has the right form and is used once.
- Each number of `[equations]` is a whole number in its range, `instances` is `"together"` or
  `"each"`; each name of `[equations] things` is drawn (not hidden); `[references] show` has
  `[equations] things`, and `kinds` keeps `"assumption"`.

For example, a `style.toml` of juneau writes `hidden` in place of `hide` under `[layout]`, the icon
`water`, which is not one of the 20, and the look `faint`, which is not a look:

```text
$ napkin compile scenarios/water_controls_wipe --variant juneau
…
scenarios/water_controls_wipe/variants/juneau/style.toml: error: layout.hidden: is not a key that this file reads; it reads layout.direction, layout.hide, layout.stocks, layout.cards_per_column, layout.card_width
scenarios/water_controls_wipe/variants/juneau/style.toml: error: icon.water: water is not an icon; the icons are target, server, shield, hospital, people, gauge, factory, tank, pipe, bolt, drop, wrench, truck, box, document, money, house, shop, sun, alert
scenarios/water_controls_wipe/variants/juneau/style.toml: error: arrows.reads: is one of "full", "light", "hidden"
```
