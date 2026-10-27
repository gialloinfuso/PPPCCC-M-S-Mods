#!/usr/bin/env python3
"""Tweak 'delay-notes' fuer die OFFIZIELLE Model:Cycles OS 1.13, kombinierbar mit hold-mute v3.

Code identisch mit gen_delaynotes.py (der in v21 steckt), nur in anderen Sprite-Masken, weil hold-mute v3 die
urspruenglichen Masken 0x401699a8 / 0x4016aa28 belegt:
  F (Anzeige, Code 86 B + Tabelle 136 B = 222 B): Maske 0x4018d918 (41x41, 328 B, Redirect-Konstante 0x400acd1a)
  D (DSP-Triolen, 128 B):                          Maske 0x40170ad8 (46x31, 184 B, Redirect-Konstante 0x400b08f6)
Beide Masken kommen in keinem bekannten 1.13-Mod vor (Modded-Cycles inkl. notes/52, drumkilla geprueft am 24.10.2026).

Hooks: 0x4004dfda (Anzeige-Thunk, 6 B, jmp), 0x400581b8 (DSP, 6 B, jsr).
Aufruf: gen_delaynotes_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gen_delaynotes as g

MF, MD = 0x4018D918, 0x40170AD8
SIZE_F, SIZE_D = 328, 184


def tweak(stock):
    g.MF, g.MD = MF, MD
    t, (cd, cf) = g.tweak(stock)
    assert len(cf) <= SIZE_F and len(cd) <= SIZE_D, (len(cf), len(cd))
    t["os"] = "1.13"
    t["description"] = ["Delay Time zeigt Notenwerte (1/1 .. 1/64, punktiert, Triolen) statt Zahlen; Triolen sind exakt.",
                        "Erzeugt von gen_delaynotes_113.py (Code wie in v21, eigene Masken)."]
    t["hooks"] = [f"{g.THUNK:#x}", f"{g.DSP:#x}"]
    t["memory"] = [{"va": f"{MF:#x}", "size": SIZE_F, "use": "Anzeige + Tabelle"},
                   {"va": f"{MD:#x}", "size": SIZE_D, "use": "DSP-Triolen"}]
    return t, (cd, cf)


if __name__ == "__main__":
    stock = open(sys.argv[1], "rb").read()
    t, (cd, cf) = tweak(stock)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("D", len(cd), "F", len(cf))
