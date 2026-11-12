# Groove tables

`grooves.json` holds the groove templates of patch 08 (groove), the same data that ends up in the firmware. Each groove
has 64 steps (16ths): for each step an offset in 1/256 of a step (signed) and an accent velocity (0–127). Grooves
shorter than 64 steps are repeated to 64 in the file; `steps` is their real length (the firmware stores 16, 32 or 64).

`patch_08_groove` lists the grooves of patch 08 in their order (groove 0 is the firmware's own Swing):

| # | Name | Steps |
|---|---|---|
| 1 | Boom Bap | 16 |
| 2 | Disco | 16 |
| 3 | Dancehall 1 | 32 |
| 4 | Dancehall 2 | 64 |
| 5 | Hip Hop | 32 |
| 6 | Jazz Rock | 32 |
| 7 | Perc 1 | 32 |
| 8 | Perc 2 | 64 |
| 9 | Perc 3 | 16 |
| 10 | Soca | 32 |

`v1_reference` lists the seven grooves of v1.0.0 – v2.2.0 (Boom Bap, Disco, Reggae, Bongo, Caixixi, Highlife, Kuduro); the
tests build the v1 reference patches with them.

The generators read this file through `src/groovetab.py`; the tests (`tests/test_groove_seq.py`) check the firmware's
timing and velocity against it.
