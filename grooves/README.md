# Groove tables

`grooves.json` holds the seven groove templates of patch 09 (groove), the same data that ends up in the firmware. Each groove
has 64 steps (16ths). For each step there is an offset in 1/256 of a step (signed) and an accent velocity (0–127).
Grooves shorter than 64 steps repeat.

| # | Name | Steps |
|---|---|---|
| 1 | Boom Bap | 16 |
| 2 | Disco | 16 |
| 3 | Reggae | 64 |
| 4 | Bongo | 64 |
| 5 | Caixixi | 16 |
| 6 | Highlife | 32 |
| 7 | Kuduro | 32 |

The generator (`src/gen_groove_113.py`) reads this file; the tests (`tests/test_groove_seq.py`) check the firmware's
timing and velocity against it.
