# Icon candidates

Rendered at 24px (real tray size) and measured for legibility.

| candidate | coverage | contrast (sd) | red pixels @24px |
|---|---|---|---|
| A screen+search  | 57% | 47.2 | 2 |
| B rewind dial    | 65% | 33.9 | 24 |
| C frame stack    | 78% | 59.9 | 13 |
| D timeline pulse | 78% | 31.9 | 2 |

Higher contrast = survives downscaling. The red-pixel count matters because the
tray uses red to mean "recording" — a candidate with only 2 red pixels at 24px
cannot signal state.

C has the best contrast; B carries the clearest recording signal.
