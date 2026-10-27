#!/usr/bin/env python3
"""Tweak 'hold-mute' v3 fuer die OFFIZIELLE Model:Cycles OS 1.13 (Port aus v21 / gen_holdmute3.py).

Verhalten wie in v21: laeuft der Sequencer, mutet ein gehaltenes Pad (T1-T6, >= ~200 ms) den Track echt und
temporaer; Loslassen hebt den Mute auf, kurzes Antippen spielt den Sound beim Loslassen.
Gestoppt (0x4005481a == 0) spielen die Pads ganz normal.

Der Code ist identisch mit gen_holdmute3.py (OS 2.0). In 1.13 liegen alle benutzten Funktionen an denselben
Adressen (geprueft: 0x4005481a, 0x4001263c, 0x4001381c, 0x400cf866, 0x4000eb90, Hooks 0x4001d05e/0x4001d0fc
Byte fuer Byte gleich). Anders sind nur:
  - Masken: 0x401699a8 (35x35, 280 B: S1 + SC) und 0x4016aa28 (35x35, 280 B: S2 + Zustand ST = MB + 0xB8, 96 B),
    wie beim alten 1.13-Hold-Mute (gen_holdmute.py). In OS 2.0 sind diese Masken anderweitig belegt.
  - UI-Tick-Kette: der Hook 0x400081f2 enthaelt ein jsr. Dessen Ziel wird aus dem Eingangs-Image gelesen und
    am Ende von SC per jmp angesprungen. Auf der Stock-1.13 ist das 0x40090f48. Haengt schon ein anderer Mod
    dort, wird er mitgekettet (das old-Feld der Tweak-JSON prueft genau diesen Zustand).

Belegt (fuer den Mod-Standard / spaetere Kombination mit fremden Mods):
  Hooks:   0x400081f2 (jsr, 6 B), 0x4001d05e (6 B), 0x4001d0fc (6 B)
  Speicher: Maske 0x401699a8 (280 B, Redirect-Konstante 0x400b1500), Maske 0x4016aa28 (280 B, Konstante 0x400b1480)
Aufruf: gen_holdmute_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gen_holdmute3 as g
from gen_solo import BASE

MA, MB = 0x401699a8, 0x4016aa28
HC = g.HC


def tweak(stock):
    assert stock[HC - BASE:HC - BASE + 2] == bytes.fromhex("4eb9"), "UI-Tick-Hook 0x400081f2 ist kein jsr"
    tick_next = struct.unpack(">I", stock[HC - BASE + 2:HC - BASE + 6])[0]
    g.MA, g.MB, g.ST, g.TICK_NEXT = MA, MB, MB + 0xB8, tick_next
    t, parts = g.tweak(stock)
    ca, cb, la, lb = parts
    assert len(ca) <= 280 and g.ST + 96 <= MB + 280
    t["os"] = "1.13"
    t["name"] = "Hold to mute (Pad halten = Track mutet, nur bei laufendem Sequencer)"
    t["description"] = [
        "Sequencer laeuft: T1-T6 gehalten (>= ca. 200 ms) = echter temporaerer Track-Mute, Loslassen hebt ihn auf.",
        "Antippen spielt den Sound beim Loslassen. Sequencer gestoppt: Pads spielen normal.",
        "Erzeugt von gen_holdmute_113.py (Port von gen_holdmute3.py / v21).",
    ]
    t["hooks"] = [f"{HC:#x}", f"{g.H1:#x}", f"{g.H2:#x}"]
    t["memory"] = [{"va": f"{MA:#x}", "size": 280, "use": "S1 + SC"},
                   {"va": f"{MB:#x}", "size": 280, "use": "S2 + Zustand"}]
    t["symbols"]["tick_next"] = f"{tick_next:#x}"
    return t, parts


if __name__ == "__main__":
    stock = open(sys.argv[1], "rb").read()
    t, (ca, cb, la, lb) = tweak(stock)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("A bytes:", len(ca), "B bytes:", len(cb), {k: hex(v) for k, v in la.items()}, "tick_next", t["symbols"]["tick_next"])
