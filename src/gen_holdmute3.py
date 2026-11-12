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

def getkit():
    """cfasm-Text: d0 = Kit"""
    return f'''
            jsr     {SING:#x}
            move.l  d0,-(sp)
            jsr     {KITF:#x}
            addq.l  #4,sp
'''

def build_a():
    from cfasm import asm, done as adone
    a = A(MA)
    asm(a, f'''
    ; ---- S1: Pad-Note-On (Stapel: ret, a2, track, note, vel, retrig)
            jsr     {PLAYING:#x}             ; Sequencer laeuft?
            tst.l   d0
            beq     s1orig                   ; gestoppt: Pad spielt normal
            move.l  8(sp),d0
            moveq   #5,d1
            cmp.l   d0,d1
            bcs     s1orig
            lsl.l   #4,d0
            lea     {ST:#x},a0
            adda.l  d0,a0                    ; Zustand des Tracks (16 B)
            move.l  {TIMER:#x},(a0)          ; Zeitpunkt des Anschlags
            move.l  4(a0),d1
            andi.l  #0x300,d1                ; alter Zustand: nur Bits 8 / 9
            move.l  12(sp),d0
            addq.l  #1,d0
            or.l    d1,d0
            move.l  d0,4(a0)                 ; Note + 1
            move.l  16(sp),8(a0)             ; Velocity
            move.l  20(sp),12(a0)            ; Retrig
            rts
    s1orig: orig    {H1:#x},6                ; ersetzte Originalbefehle (aus dem Image), weiter
            jmp     {H1 + 6:#x}
    ; ---- SC: 30-Hz-Tick (Stapel: d0 als Argument fuer 0x40090f48)
    sc:     lea     -12(sp),sp
            movem.l d2-d3/a2,(sp)
            moveq   #0,d2
            lea     {ST:#x},a2
    loop:   move.l  4(a2),d0                 ; Zustand
            beq     next                     ; leer
            btst    #9,d0
            bne     next                     ; schon erledigt
            move.l  {TIMER:#x},d0
            sub.l   (a2),d0
            cmpi.l  #{HOLD:#x},d0
            bcs     next                     ; noch nicht lange genug gehalten
            move.l  4(a2),d0
            bset    #9,d0                    ; erledigt
            move.l  d0,4(a2)
{getkit()}
            move.l  d0,d3                    ; Kit
            move.l  d2,-(sp)
            move.l  d3,-(sp)
            jsr     {GETM:#x}                ; Mute(Kit, Track)
            addq.l  #8,sp
            tst.b   d0
            bne     next                     ; war schon gemutet: nichts anfassen
            pea     1.w
            pea     1.w
            move.l  d2,-(sp)
            move.l  d3,-(sp)
            jsr     {SETM:#x}                ; muten
            lea     16(sp),sp
            move.l  4(a2),d0
            bset    #8,d0                    ; von uns gemutet
            move.l  d0,4(a2)
    next:   addq.l  #1,d2
            lea     16(a2),a2
            moveq   #6,d0
            cmp.l   d2,d0
            bne     loop
            movem.l (sp),d2-d3/a2
            lea     12(sp),sp
            jmp     {TICK_NEXT:#x}           ; naechstes Glied der Tick-Kette
    ''')
    code = adone(a)
    assert len(code) <= 272, len(code)
    return code, a.lab

def build_b(s1orig):
    from cfasm import asm, done as adone
    a = A(MB)
    asm(a, f'''
    ; ---- S2: Pad-Note-Off (Stapel: ret, a2, track, note)
            move.l  8(sp),d0
            moveq   #5,d1
            cmp.l   d0,d1
            bcs     s2orig
            lsl.l   #4,d0
            lea     {ST:#x},a0
            adda.l  d0,a0
            move.l  4(a0),d1                 ; Zustand
            beq     s2orig
            clr.l   4(a0)
            btst    #9,d1
            bne     s2hold                   ; Halten schon erkannt
            move.l  {TIMER:#x},d0
            sub.l   (a0),d0
            cmpi.l  #{HOLD:#x},d0
            bcc     s2hold
            andi.l  #0xff,d1                 ; kurz angetippt: Note-On jetzt nachholen
            move.l  12(a0),-(sp)
            move.l  8(a0),-(sp)
            subq.l  #1,d1
            move.l  d1,-(sp)
            move.l  20(sp),-(sp)
            move.l  20(sp),-(sp)
            jsr     {s1orig:#x}
            lea     20(sp),sp
    s2orig: orig    {H2:#x},6                ; ersetzte Originalbefehle (aus dem Image), weiter
            jmp     {H2 + 6:#x}
    s2hold: btst    #8,d1
            beq     s2done                   ; von uns gemutet?
{getkit()}
            pea     1.w
            clr.l   -(sp)
            move.l  16(sp),-(sp)
            move.l  d0,-(sp)
            jsr     {SETM:#x}                ; wieder entmuten
            lea     16(sp),sp
    s2done: rts
    ''')
    code = adone(a)
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
