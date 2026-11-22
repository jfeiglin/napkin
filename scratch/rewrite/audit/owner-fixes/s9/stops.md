# for the owner: stop near simultaneous bounds, fix or diagnostic?

The generator recorded 135 Component stock-bound failures and 11 MovingDeclared trial-budget stops on macOS at ca5a674. Each of the 146 minimized models reproduced the original outcome. Each ran to its horizon at ee36192. Models from 26 pairs or variants reduce to identical source text, leaving 120 distinct model texts. Every seed and variant retains its own file in the archive.

The 2,000-seed deep tier added two reversible-tank variants, giving 148 stopped variants across the two collections. Both additional runs had an upper-bound contact at the start of an inward step. The corrected engine completed both runs and matched their analytic terminal inventories. [Deep seeds 437 and 1553, minimized models and outcomes](../final/deep-bounds/stops.md).

The simultaneous-bound family itself completed every run. The cases below arose in the reversible-tank family. Reducing some of them to a single stock shows that a second simultaneous contact was unnecessary for those stops. The 11 solver cases reached the generator’s 1,500-evaluation cap. [Minimized models and machine-readable index](minimized-stops.zip) · [Original observations and full models](stopped-models.jsonl.gz)

| Seed | Variant | Minimized model in the archive | Baseline observation |
|---:|---|---|---|
| 0 | component.event | models/000-component.event.scn | Material state-bound violation for yard.b at 1 h |
| 0 | component.plain | models/000-component.plain.scn | Material state-bound violation for yard.b at 1 h |
| 1 | component.event | models/001-component.event.scn | Material state-bound violation for yard.a at 0.478515625 h |
| 1 | component.plain | models/001-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 5 | component.event | models/005-component.event.scn | Material state-bound violation for yard.a at 1.507324219 h |
| 9 | component.event | models/009-component.event.scn | Material state-bound violation for yard.a at 1.3125 h |
| 9 | component.plain | models/009-component.plain.scn | Material state-bound violation for yard.a at 1.3125 h |
| 13 | component.event | models/013-component.event.scn | Material state-bound violation for yard.b at 0.9689941406 h |
| 13 | component.plain | models/013-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 17 | component.event | models/017-component.event.scn | Material state-bound violation for yard.b at 1.421875 h |
| 17 | component.plain | models/017-component.plain.scn | Material state-bound violation for yard.b at 1.421875 h |
| 25 | component.event | models/025-component.event.scn | Material state-bound violation for yard.a at 1.03125 h |
| 25 | component.plain | models/025-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 29 | component.event | models/029-component.event.scn | Material state-bound violation for yard.a at 0.35546875 h |
| 29 | component.plain | models/029-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 33 | component.event | models/033-component.event.scn | Material state-bound violation for yard.b at 1.076660156 h |
| 33 | component.plain | models/033-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 37 | component.event | models/037-component.event.scn | Material state-bound violation for yard.b at 1.589355469 h |
| 37 | component.plain | models/037-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 39 | declared.plain | models/039-declared.plain.scn | 1,500 solver evaluations, accepted through 0.99997356 h |
| 41 | component.event | models/041-component.event.scn | Material state-bound violation for yard.a at 1.03125 h |
| 41 | component.plain | models/041-component.plain.scn | Material state-bound violation for yard.a at 1.03125 h |
| 45 | component.event | models/045-component.event.scn | Material state-bound violation for yard.a at 0.263671875 h |
| 45 | component.plain | models/045-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 49 | component.event | models/049-component.event.scn | Material state-bound violation for yard.a at 0.3515625 h |
| 49 | component.plain | models/049-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 53 | component.event | models/053-component.event.scn | Material state-bound violation for yard.b at 1.640625 h |
| 53 | component.plain | models/053-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 57 | component.event | models/057-component.event.scn | Material state-bound violation for yard.b at 0.60546875 h |
| 57 | component.plain | models/057-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 61 | component.event | models/061-component.event.scn | Material state-bound violation for yard.a at 0.7265625 h |
| 61 | component.plain | models/061-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 73 | component.event | models/073-component.event.scn | Material state-bound violation for yard.b at 0.6811523438 h |
| 73 | component.plain | models/073-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 77 | component.event | models/077-component.event.scn | Material state-bound violation for yard.b at 0.84375 h |
| 77 | component.plain | models/077-component.plain.scn | Material state-bound violation for yard.b at 0.84375 h |
| 81 | component.event | models/081-component.event.scn | Material state-bound violation for yard.a at 1.06640625 h |
| 81 | component.plain | models/081-component.plain.scn | Material state-bound violation for yard.a at 1.421875 h |
| 85 | component.event | models/085-component.event.scn | Material state-bound violation for yard.a at 0.328125 h |
| 85 | component.plain | models/085-component.plain.scn | Material state-bound violation for yard.a at 0.875 h |
| 89 | component.event | models/089-component.event.scn | Material state-bound violation for yard.a at 0.140625 h |
| 89 | component.plain | models/089-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 93 | component.event | models/093-component.event.scn | Material state-bound violation for yard.b at 0.75 h |
| 93 | component.plain | models/093-component.plain.scn | Material state-bound violation for yard.b at 0.75 h |
| 97 | component.event | models/097-component.event.scn | Material state-bound violation for yard.b at 0.65625 h |
| 97 | component.plain | models/097-component.plain.scn | Material state-bound violation for yard.b at 0.875 h |
| 101 | component.event | models/101-component.event.scn | Material state-bound violation for yard.a at 1.059570312 h |
| 101 | component.plain | models/101-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 105 | component.event | models/105-component.event.scn | Material state-bound violation for yard.a at 0.423828125 h |
| 105 | component.plain | models/105-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 111 | declared.plain | models/111-declared.plain.scn | 1,500 solver evaluations, accepted through 0.99997356 h |
| 113 | component.event | models/113-component.event.scn | Material state-bound violation for yard.b at 0.3125 h |
| 113 | component.plain | models/113-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 117 | component.event | models/117-component.event.scn | Material state-bound violation for yard.b at 0.28125 h |
| 117 | component.plain | models/117-component.plain.scn | Material state-bound violation for yard.b at 0.75 h |
| 119 | declared.event | models/119-declared.event.scn | 1,500 solver evaluations, accepted through 1.124967435 h |
| 119 | declared.plain | models/119-declared.plain.scn | 1,500 solver evaluations, accepted through 1.124967435 h |
| 121 | component.event | models/121-component.event.scn | Material state-bound violation for yard.a at 0.7265625 h |
| 121 | component.plain | models/121-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 125 | component.event | models/125-component.event.scn | Material state-bound violation for yard.a at 0.7265625 h |
| 125 | component.plain | models/125-component.plain.scn | Material state-bound violation for yard.a at 0.96875 h |
| 129 | component.event | models/129-component.event.scn | Material state-bound violation for yard.a at 1.33984375 h |
| 129 | component.plain | models/129-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 133 | component.event | models/133-component.event.scn | Material state-bound violation for yard.b at 1.0546875 h |
| 133 | component.plain | models/133-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 137 | component.event | models/137-component.event.scn | Material state-bound violation for yard.b at 0.263671875 h |
| 137 | component.plain | models/137-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 141 | component.event | models/141-component.event.scn | Material state-bound violation for yard.a at 1.57421875 h |
| 141 | component.plain | models/141-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 145 | component.event | models/145-component.event.scn | Material state-bound violation for yard.a at 0.6875 h |
| 145 | component.plain | models/145-component.plain.scn | Material state-bound violation for yard.a at 0.6875 h |
| 149 | component.event | models/149-component.event.scn | Material state-bound violation for yard.a at 0.24609375 h |
| 149 | component.plain | models/149-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 157 | component.event | models/157-component.event.scn | Material state-bound violation for yard.b at 1.3125 h |
| 157 | component.plain | models/157-component.plain.scn | Material state-bound violation for yard.b at 1.3125 h |
| 159 | declared.event | models/159-declared.event.scn | 1,500 solver evaluations, accepted through 1.374962905 h |
| 159 | declared.plain | models/159-declared.plain.scn | 1,500 solver evaluations, accepted through 1.374962905 h |
| 161 | component.event | models/161-component.event.scn | Material state-bound violation for yard.a at 1.57421875 h |
| 161 | component.plain | models/161-component.plain.scn | Material state-bound violation for yard.a at 1.57421875 h |
| 165 | component.event | models/165-component.event.scn | Material state-bound violation for yard.a at 0.1538085938 h |
| 165 | component.plain | models/165-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 169 | component.event | models/169-component.event.scn | Material state-bound violation for yard.a at 0.8173828125 h |
| 169 | component.plain | models/169-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 173 | component.event | models/173-component.event.scn | Material state-bound violation for yard.b at 0.4614257812 h |
| 173 | component.plain | models/173-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 177 | component.event | models/177-component.event.scn | Material state-bound violation for yard.b at 0.234375 h |
| 177 | component.plain | models/177-component.plain.scn | Material state-bound violation for yard.b at 0.9375 h |
| 181 | component.event | models/181-component.event.scn | Material state-bound violation for yard.a at 0.875 h |
| 181 | component.plain | models/181-component.plain.scn | Material state-bound violation for yard.a at 0.875 h |
| 185 | component.event | models/185-component.event.scn | Material state-bound violation for yard.a at 0.421875 h |
| 185 | component.plain | models/185-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 189 | component.event | models/189-component.event.scn | Material state-bound violation for yard.a at 1.125 h |
| 189 | component.plain | models/189-component.plain.scn | Material state-bound violation for yard.a at 1.125 h |
| 193 | component.event | models/193-component.event.scn | Material state-bound violation for yard.b at 1.21875 h |
| 193 | component.plain | models/193-component.plain.scn | Material state-bound violation for yard.b at 1.21875 h |
| 201 | component.event | models/201-component.event.scn | Material state-bound violation for yard.a at 0.3515625 h |
| 201 | component.plain | models/201-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 205 | component.event | models/205-component.event.scn | Material state-bound violation for yard.a at 1.015136719 h |
| 205 | component.plain | models/205-component.plain.scn | Material state-bound violation for yard.a at 1.353515625 h |
| 209 | component.event | models/209-component.event.scn | Material state-bound violation for yard.a at 1.21875 h |
| 209 | component.plain | models/209-component.plain.scn | Material state-bound violation for yard.a at 1.21875 h |
| 213 | component.event | models/213-component.event.scn | Material state-bound violation for yard.b at 0.24609375 h |
| 213 | component.plain | models/213-component.plain.scn | Material state-bound violation for yard.b at 0.65625 h |
| 217 | component.event | models/217-component.event.scn | Material state-bound violation for yard.b at 0.84375 h |
| 217 | component.plain | models/217-component.plain.scn | Material state-bound violation for yard.b at 0.84375 h |
| 221 | component.event | models/221-component.event.scn | Material state-bound violation for yard.a at 0.5 h |
| 221 | component.plain | models/221-component.plain.scn | Material state-bound violation for yard.a at 0.5 h |
| 225 | component.event | models/225-component.event.scn | Material state-bound violation for yard.a at 1.5 h |
| 225 | component.plain | models/225-component.plain.scn | Material state-bound violation for yard.a at 1.5 h |
| 229 | component.event | models/229-component.event.scn | Material state-bound violation for yard.a at 1.21875 h |
| 229 | component.plain | models/229-component.plain.scn | Material state-bound violation for yard.a at 1.21875 h |
| 233 | component.event | models/233-component.event.scn | Material state-bound violation for yard.b at 1.362304688 h |
| 233 | component.plain | models/233-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 237 | component.event | models/237-component.event.scn | Material state-bound violation for yard.b at 1.3125 h |
| 237 | component.plain | models/237-component.plain.scn | Material state-bound violation for yard.b at 1.3125 h |
| 239 | declared.event | models/239-declared.event.scn | 1,500 solver evaluations, accepted through 0.7499702968 h |
| 239 | declared.plain | models/239-declared.plain.scn | 1,500 solver evaluations, accepted through 0.7499702968 h |
| 243 | declared.event | models/243-declared.event.scn | 1,500 solver evaluations, accepted through 1.624970796 h |
| 245 | component.event | models/245-component.event.scn | Material state-bound violation for yard.a at 0.5126953125 h |
| 245 | component.plain | models/245-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 249 | component.event | models/249-component.event.scn | Material state-bound violation for yard.a at 0.8173828125 h |
| 249 | component.plain | models/249-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 253 | component.event | models/253-component.event.scn | Material state-bound violation for yard.b at 1.333007812 h |
| 253 | component.plain | models/253-component.plain.scn | Material state-bound violation for yard.b at 1.5234375 h |
| 257 | component.event | models/257-component.event.scn | Material state-bound violation for yard.b at 0.625 h |
| 257 | component.plain | models/257-component.plain.scn | Material state-bound violation for yard.b at 0.625 h |
| 261 | component.event | models/261-component.event.scn | Material state-bound violation for yard.a at 0.7734375 h |
| 261 | component.plain | models/261-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 265 | component.event | models/265-component.event.scn | Material state-bound violation for yard.a at 0.90234375 h |
| 265 | component.plain | models/265-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 269 | component.event | models/269-component.event.scn | Material state-bound violation for yard.a at 0.1171875 h |
| 269 | component.plain | models/269-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 273 | component.event | models/273-component.event.scn | Material state-bound violation for yard.b at 0.328125 h |
| 273 | component.plain | models/273-component.plain.scn | Material state-bound violation for yard.b at 0.875 h |
| 277 | component.event | models/277-component.event.scn | Material state-bound violation for yard.b at 0.3515625 h |
| 277 | component.plain | models/277-component.plain.scn | Material state-bound violation for yard.b at 0 h |
| 281 | component.event | models/281-component.event.scn | Material state-bound violation for yard.a at 0.341796875 h |
| 281 | component.plain | models/281-component.plain.scn | Material state-bound violation for yard.a at 0 h |
| 283 | declared.event | models/283-declared.event.scn | 1,500 solver evaluations, accepted through 1.999957141 h |
| 283 | declared.plain | models/283-declared.plain.scn | 1,500 solver evaluations, accepted through 1.999957141 h |
| 289 | component.event | models/289-component.event.scn | Material state-bound violation for yard.a at 0.5625 h |
| 289 | component.plain | models/289-component.plain.scn | Material state-bound violation for yard.a at 0.5625 h |
| 293 | component.event | models/293-component.event.scn | Material state-bound violation for yard.b at 0.75 h |
| 293 | component.plain | models/293-component.plain.scn | Material state-bound violation for yard.b at 0.75 h |
| 297 | component.event | models/297-component.event.scn | Material state-bound violation for yard.b at 1.399658203 h |
| 297 | component.plain | models/297-component.plain.scn | Material state-bound violation for yard.b at 0 h |
