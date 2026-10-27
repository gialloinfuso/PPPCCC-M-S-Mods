#!/usr/bin/env python3
"""Tweak 'hold-mute' v3 fuer Modded Cycles OS 2.0: wie v2, aber nur bei laufendem Sequencer (0x4005481a != 0); gestoppt spielen die Pads normal.
Masken neu (OS 2.0 belegt die alten), UI-Tick-Kette ueber das OS-2.0-Ziel 0x4018f4b4.

v2 (Model:Cycles OS 1.13): Pad (T1-T6) halten (>= ~200 ms) setzt den normalen Mute des Tracks
(setMute wie im Latch-Mute-Modus: Sequencer-Noten fallen weg, Ausklang laeuft weiter); Loslassen hebt ihn wieder auf.
Kurzes Antippen spielt den Sound beim Loslassen.

S1 (Hook 0x4001d05e, Pad-Note-On): merkt Zeit/Note/Velocity/Retrig, verschluckt die Note.
SC (Hook 0x400081f2, 30-Hz-UI-Tick; ersetzt das jsr durch ein jsr, Ende per jmp = Tail-Call): Pad >= HOLD gehalten -> Track mit 0x4001381c stummschalten (nur wenn er es nicht schon war).
S2 (Hook 0x4001d0fc, Pad-Note-Off): Tippen -> Note-On nachholen + Note-Off; Halten -> verschlucken, Mute aufheben (falls von uns).
Zustand 6 x 16 B im Schwanz von Maske B: +0 Zeit, +4 (Note+1) | 0x100 (von uns gemutet) | 0x200 (Halten erledigt), +8 Vel, +12 Retrig.
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
MA, MB = 0x4018FF64, 0x4018D918          # 34x34 (272 B) und 41x41 (328 B)
ST = MB + 0xB8
TICK_NEXT = 0x4018F4B4                     # OS 2.0 leitet den UI-Tick schon hierher (danach 0x40090f48)
PLAYING = 0x4005481a
TIMER = 0xFC07000C
HOLD = 0x01A00000                 # ~201,7 ms
GETM, SETM, SING, KITF = 0x4001263C, 0x4001381C, 0x400CF866, 0x4000EB90
H1, H2, HC = 0x4001D05E, 0x4001D0FC, 0x400081F2
H1_CK, H2_CK = (6, '5ce8271cb6586ad4860e3aa6705562a63e60438793d61114cc7010405aa0c780'), (6, '62084066504316135ae81e12d4ecc99c9919db42425cc8fa2be3ea0a8ef3bbc4')   # Laenge + SHA-256 der ersetzten Originalbefehle
BEQ, BNE, BCS, BCC = 0x7, 0x6, 0x5, 0x4

def getkit(a):                    # d0 = Kit
    a.w(0x4EB9); a.l32(SING); a.w(0x2F00, 0x4EB9); a.l32(KITF); a.w(0x588F)

def build_a():
    a = A(MA)
    # ---- S1: Pad-Note-On (Stack: ret, a2, track, note, vel, retrig)
    a.w(0x4EB9); a.l32(PLAYING); a.w(0x4A80)         # jsr Sequencer-laeuft ; tst.l d0
    a.bcc(BEQ, 's1orig')                              # gestoppt: Pad spielt normal
    a.w(0x202F, 0x0008, 0x7205, 0xB280)               # move.l 8(a7),d0 ; moveq #5,d1 ; cmp.l d0,d1
    a.bcc(BCS, 's1orig')
    a.w(0xE988, 0x41F9); a.l32(ST); a.w(0xD1C0)       # lsl.l #4,d0 ; lea ST,a0 ; adda.l d0,a0
    a.w(0x20B9); a.l32(TIMER)                         # move.l TIMER,(a0)
    a.w(0x2228, 0x0004, 0x0281); a.l32(0x300)         # d1 = alter Zustand & 0x300
    a.w(0x202F, 0x000C, 0x5280, 0x8081, 0x2140, 0x0004)   # d0 = note+1 | d1 ; move.l d0,4(a0)
    a.w(0x216F, 0x0010, 0x0008, 0x216F, 0x0014, 0x000C)   # vel, retrig
    a.w(0x4E75)
    a.label('s1orig')
    a.orig(H1, 6); a.w(0x4EF9); a.l32(H1 + 6)        # ersetzte Originalbefehle (aus dem Image), weiter
    # ---- SC: 30-Hz-Tick (Stack: d0 als Argument fuer 0x40090f48)
    a.label('sc')
    a.w(0x4FEF, 0xFFF4, 0x48D7, 0x040C)               # lea -12(a7),a7 ; movem.l d2-d3/a2,(a7)
    a.w(0x7400, 0x45F9); a.l32(ST)                    # moveq #0,d2 ; lea ST,a2
    a.label('loop')
    a.w(0x202A, 0x0004); a.bcc(BEQ, 'next')           # d0 = Zustand ; leer
    a.w(0x0800, 0x0009); a.bcc(BNE, 'next')           # btst #9,d0 ; schon erledigt
    a.w(0x2039); a.l32(TIMER); a.w(0x9092)            # d0 = TIMER ; sub.l (a2),d0
    a.w(0x0C80); a.l32(HOLD); a.bcc(BCS, 'next')
    a.w(0x202A, 0x0004, 0x08C0, 0x0009, 0x2540, 0x0004)   # bset #9 -> erledigt
    getkit(a)
    a.w(0x2600)                                       # move.l d0,d3  (Kit)
    a.w(0x2F02, 0x2F03, 0x4EB9); a.l32(GETM); a.w(0x508F, 0x4A00)   # getMute(kit,track) ; addq #8 ; tst.b
    a.bcc(BNE, 'next')                                # war schon gemutet: nichts anfassen
    a.w(0x4878, 0x0001, 0x4878, 0x0001, 0x2F02, 0x2F03, 0x4EB9); a.l32(SETM); a.w(0x4FEF, 0x0010)
    a.w(0x202A, 0x0004, 0x08C0, 0x0008, 0x2540, 0x0004)   # bset #8 -> von uns gemutet
    a.label('next')
    a.w(0x5282, 0x45EA, 0x0010, 0x7006, 0xB082)       # addq #1,d2 ; lea 16(a2),a2 ; moveq #6,d0 ; cmp.l d2,d0
    a.bcc(BNE, 'loop')
    a.w(0x4CD7, 0x040C, 0x4FEF, 0x000C, 0x4EF9); a.l32(TICK_NEXT)   # restore ; jmp naechstes Glied (OS 2.0)
    code = a.done()
    assert len(code) <= 272, len(code)
    return code, a.lab

def build_b(s1orig):
    a = A(MB)
    # ---- S2: Pad-Note-Off (Stack: ret, a2, track, note)
    a.w(0x202F, 0x0008, 0x7205, 0xB280)
    a.bcc(BCS, 's2orig')
    a.w(0xE988, 0x41F9); a.l32(ST); a.w(0xD1C0)
    a.w(0x2228, 0x0004); a.bcc(BEQ, 's2orig')         # d1 = Zustand
    a.w(0x42A8, 0x0004)                               # clr.l 4(a0)
    a.w(0x0801, 0x0009); a.bcc(BNE, 's2hold')         # btst #9,d1 : Halten schon erkannt
    a.w(0x2039); a.l32(TIMER); a.w(0x9090)
    a.w(0x0C80); a.l32(HOLD); a.bcc(BCC, 's2hold')
    a.w(0x0281); a.l32(0xFF)                          # andi.l #0xFF,d1
    a.w(0x2F28, 0x000C, 0x2F28, 0x0008, 0x5381, 0x2F01)
    a.w(0x2F2F, 0x0014, 0x2F2F, 0x0014)
    a.w(0x4EB9); a.l32(s1orig)
    a.w(0x4FEF, 0x0014)
    a.label('s2orig')
    a.orig(H2, 6); a.w(0x4EF9); a.l32(H2 + 6)        # ersetzte Originalbefehle (aus dem Image), weiter
    a.label('s2hold')
    a.w(0x0801, 0x0008); a.bcc(BEQ, 's2done')         # btst #8,d1 : von uns gemutet?
    getkit(a)                                         # d0 = Kit
    a.w(0x4878, 0x0001, 0x42A7, 0x2F2F, 0x0010, 0x2F00, 0x4EB9); a.l32(SETM); a.w(0x4FEF, 0x0010)
    a.label('s2done')
    a.w(0x4E75)
    code = a.done()
    assert len(code) <= 0xB8, len(code)
    return code, a.lab

def tweak(stock):
    ca, la = build_a(); cb, lb = build_b(la['s1orig'])
    sw = lambda va, new: {"off": va - BASE, "old": stock[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    jmp = lambda t: bytes.fromhex("4ef9") + struct.pack('>I', t)
    assert matches(stock, H1, H1_CK)
    assert matches(stock, H2, H2_CK)
    assert stock[HC-BASE:HC-BASE+6] == bytes.fromhex("4eb9") + struct.pack(">I", TICK_NEXT)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    writes = [sw(MA, ca), sw(ST, bytes(96)), sw(MB, cb), sprites.redirect_write(MA), sprites.redirect_write(MB),
              sw(H1, jmp(MA)), sw(H2, jmp(MB)), sw(HC, bytes.fromhex('4eb9') + struct.pack('>I', la['sc']))]
    writes.sort(key=lambda w: w["off"])
    return {"id": "hold-mute", "order": 64, "name": "Pad halten = Track mutet (wie Latch-Mute)",
            "description": ["T1-T6 gehalten (>= ca. 200 ms): normaler Track-Mute (Sequencer-Noten fallen weg, Ausklang bleibt), Loslassen hebt ihn auf.",
                            "Antippen spielt den Sound beim Loslassen. Erzeugt von gen_holdmute.py."],
            "device": "Model:Cycles", "os": "2.0", "section": 3, "conflicts": ["level-pan-values"],
            "symbols": {"state": f"{ST:#x}", "tick": f"{la['sc']:#x}"},
            "writes": writes}, (ca, cb, la, lb)

if __name__ == "__main__":
    stock = open(sys.argv[1], 'rb').read()
    t, (ca, cb, la, lb) = tweak(stock)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("A bytes:", len(ca), "B bytes:", len(cb), la)
