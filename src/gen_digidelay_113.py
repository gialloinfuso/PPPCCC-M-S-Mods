#!/usr/bin/env python3
"""Tweak 'digi-delay' fuer die OFFIZIELLE Model:Cycles OS 1.13: Digital Delay auf dem Delay-Platz (Port aus v21, mit mehr Charakter).
Setzt 'chorus', 'phaser' (Umschaltung/Namen/H4) und 'delay-notes' (Zeit inkl. Triolen ueber deren DSP-Routine) voraus.
  TRACK + Delay Time: Delay (Original) <-> Digital. Gespeichert: Byte 0x404e9b5c, invertiert (Werkseinstellung 1 = Original,
  0 = Digital; die Stock-1.13 setzt es nur beim Reset auf 1 und liest es nie). Namen Digi Send / Digi Time / Digi Fdbk.

Klang wie v21 (Boss DD-2/DD-3-Vorbild, Feedback-Kurve (3t - t^3)/2, bis 5.4 s, Zeile 0x4a400000 untere Haelfte), aber
'Gegenteil vom Stock-Delay' (Pips Wunsch 25.10.2026): im Rueckkopplungsweg
  - Hochpass 1-Pol ~240 Hz statt ~120 Hz (Koeffizient 1/32 statt 1/64): jede Wiederholung wird duenner, kumulativ
    (200 Hz: ca. -4 dB je Runde, 1 kHz: ca. -0.2 dB je Runde)
  - Tiefpass 1-Pol ~12.8 kHz statt ~7.5 kHz (a = 13/16 statt 5/8), ueberlauffest als gewichtetes Mittel + sats:
    die Wiederholungen bleiben hell (das Stock-Delay dunkelt mit ~1.4 kHz ab).
  CHAR = False erzeugt den Klang exakt wie v21 (dazu LOUD = False: Ausgang x4 statt x6).
Haken (1.13-Mixer, direkt statt OS-2.0-Wrapper, gleiche Stack-Belegung):
  0x4005699c jsr Delay -> jsr D (D springt im Original-Modus nach 0x40057488)
  0x40056a3c jsr Schreib-DMA -> jsr W (W verschiebt im Digital-Modus den DMA-Index in die obere Haelfte, dann 0x400573fa)
Masken: Schleife 0x40185f48 (34x34) | Setup 0x40160e6c (35x35) | Delay-Namen 0x40160b6c (35x35) | W 0x4014a890 (27x27)
RAM: Zustand 0x4a33c140..0x4a33c153 (v21: 0x4a33a180, liegt hier im Chorus-Puffer).
Aufruf: gen_digidelay_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
from gen_chorusfx import check_cf
import gen_fx4 as fx
import gen_chorus_113 as ch
import gen_phaser_113 as ph
import gen_delaynotes_113 as dn

M_DL, M_DS, M_NX, M_W = 0x40185F48, 0x40160E6C, 0x40160B6C, 0x4014A890
SIZE = {M_DL: 272, M_DS: 280, M_NX: 280, M_W: 108}
DSTATE = 0x4233C140                 # gecachter Alias von 0x4a33c140
D_HOOK, W_HOOK = 0x4005699C, 0x40056A3C
DMODE = fx.DMODE
CHAR = True
LOUD = True                                  # Ausgang x6 statt x4 (v21: x4)
NE, EQ, PL = 0x6, 0x7, 0xA


def build_dl():
    """fx.build_dl mit dem Charakter-Filter (CHAR). Register wie dort: d0 s, d6 Tiefpass, a6 Hochpass-Tiefanteil."""
    from cfasm import asm, done as adone
    if CHAR:
        filt = '''
    ; Tiefpass a = 13/16: lp = (s - 3s/16) + 3lp/16, sats
            move.l  d0,d2
            asr.l   #3,d2
            move.l  d2,d7
            asr.l   #1,d7
            add.l   d7,d2                    ; 3s/16
            sub.l   d2,d0                    ; 13s/16
            move.l  d6,d2
            asr.l   #3,d2
            move.l  d2,d7
            asr.l   #1,d7
            add.l   d7,d2                    ; 3lp/16
            add.l   d2,d0
            sats.l  d0
            move.l  d0,d6
    ; Hochpass a = 1/32 (~240 Hz): h = lp - tief ; q = h>>5 ; tief += q ; h -= q
            move.l  d6,d2
            move.l  a6,d7
            sub.l   d7,d2
            move.l  d2,d0
            asr.l   #5,d0
            add.l   d0,d7
            movea.l d7,a6
            sub.l   d0,d2'''
    else:
        filt = '''
            move.l  d0,d2
            asr.l   #1,d2
            move.l  d6,d7
            asr.l   #1,d7
            sub.l   d7,d2
            move.l  d2,d7
            asr.l   #2,d7
            add.l   d7,d2
            add.l   d2,d6
            move.l  d6,d2
            move.l  a6,d7
            sub.l   d7,d2
            move.l  d2,d0
            asr.l   #6,d0
            add.l   d0,d7
            movea.l d7,a6
            sub.l   d0,d2'''
    if LOUD:                                # x6 (+3.5 dB gegenueber x4, Pips Wunsch 25.10.2026): o1 = 2y, o2 = 4y, out = o2 + o1
        gain = '''
            add.l   d1,d1
            sats.l  d1
            move.l  d1,d0
            add.l   d1,d1
            sats.l  d1
            add.l   d0,d1
            sats.l  d1'''
    else:
        gain = '''
            add.l   d1,d1
            sats.l  d1
            add.l   d1,d1
            sats.l  d1'''
    a = A(M_DL)
    asm(a, f'''
    ; Lesekopf gleitet zur Ziel-Verzoegerung (a4), d4 = aktuelle Verzoegerung
    loop:   move.l  a4,d0
            sub.l   d4,d0
            move.l  d0,d7
            asr.l   #8,d7
            asr.l   #5,d7
            bne     add
            tst.l   d0
            beq     nost
            move.l  d3,d1
            andi.l  #3,d1
            bne     nost
            moveq   #1,d7
            tst.l   d0
            bpl     add
            moveq   #-1,d7
    add:    add.l   d7,d4
    nost:   move.l  d3,d0
            sub.l   d4,d0
            andi.l  #{fx.LMASK:#x},d0
            lsl.l   #3,d0
            move.l  0(a2,d0.l),d1            ; y = Leitung
            move.l  a5,d7
            move.l  d1,d0
            asr.l   #8,d0
            asr.l   #7,d0
            muls.l  d7,d0
            move.l  d1,d2
            andi.l  #0x7fff,d2
            muls.l  d7,d2
            asr.l   #8,d2
            asr.l   #7,d2
            add.l   d2,d0                    ; g*y
            move.l  (a0)+,d2
            asr.l   #3,d2
            move.l  (a0)+,d7
            asr.l   #3,d7
            add.l   d7,d2                    ; x = (L + R)/8
            add.l   d2,d0
            sats.l  d0                       ; s = sats(x + g*y){filt}
            move.l  d3,d0
            lsl.l   #3,d0
            move.l  d2,0(a2,d0.l)            ; in die Leitung
            move.l  d2,4(a2,d0.l){gain}
            move.l  d1,(a1)+
            move.l  d1,(a1)+
            addq.l  #1,d3
            andi.l  #{fx.LMASK:#x},d3
            subq.l  #1,d5
            bne     loop
            move.l  d3,(a3)
            move.l  d4,4(a3)
            move.l  d6,12(a3)
            move.l  a6,16(a3)
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ''')
    code = adone(a); check_cf(code, M_DL); assert len(code) <= SIZE[M_DL], len(code)
    return code


def build(img):
    fx.M_DL, fx.M_DS, fx.M_NX, fx.M_W, fx.DSTATE, fx.DNOTES = M_DL, M_DS, M_NX, M_W, DSTATE, dn.MD
    dl = build_dl()
    ds, d_addr = fx.build_ds(M_DL)
    wc, w_addr = fx.build_w()
    nx, nx_addr = fx.build_nx(img)
    return dict(dl=dl, ds=ds, wc=wc, nx=nx, d=d_addr, w=w_addr, nx_addr=nx_addr)


def apply(img, t):
    b = bytearray(img)
    for x in t['writes']:
        o = bytes.fromhex(x['old']); assert b[x['off']:x['off'] + len(o)] == o
        b[x['off']:x['off'] + len(o)] = bytes.fromhex(x['new'])
    return b


def tweak(img):
    D = build(img)
    imgp = apply(apply(apply(img, dn.tweak(img)[0]), ch.tweak(img)[0]), ph.tweak(img)[0])   # Stand mit den Voraussetzungen
    _, popt = ph.phaser_opts()
    parts, lab, _ = ch.build(img, phaser=popt, nx=D['nx_addr'], extra_entries=[(15, DMODE, 1, [2], 1)])
    own = {M_DL: D['dl'], M_DS: D['ds'], M_NX: D['nx'], M_W: D['wc']}
    for va, b in own.items():
        assert len(b) <= SIZE[va], (hex(va), len(b))
    sw = lambda va, new: {"off": va - BASE, "old": bytes(imgp[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    assert imgp[D_HOOK-BASE:D_HOOK-BASE+6] == jsr(fx.STOCK) and imgp[W_HOOK-BASE:W_HOOK-BASE+6] == jsr(fx.WRITE_DMA)
    assert matches(imgp, dn.MD, dn.g.DSP_CK), "Delay-Noten-Routine fehlt"
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = []
    for va, b in own.items():
        w += [sw(va, b), sprites.redirect_write(va)]
    changed = []
    for va in (ch.M_UI, ch.M_NAMES, ch.M_H4):
        new = parts[va]
        if bytes(imgp[va - BASE:va - BASE + len(new)]) != new:
            w.append(sw(va, new)); changed.append(f"{va:#x}")
    w += [sw(D_HOOK, jsr(D['d'])), sw(W_HOOK, jsr(D['w']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "digi-delay", "order": 68, "name": "Digital Delay auf dem Delay-Platz (TRACK + Delay Time)",
         "description": ["Delay <-> Digital Delay (TRACK + Delay Time). Hell und klar, jede Wiederholung etwas duenner (Hochpass ~240 Hz in der Schleife).",
                         "Erzeugt von gen_digidelay_113.py (v21-Delay mit Charakter-Filter)."],
         "device": "Model:Cycles", "os": "1.13", "section": 3, "requires": ["delay-notes", "chorus", "phaser"],
         "hooks": [f"{D_HOOK:#x}", f"{W_HOOK:#x}"], "changes": changed, "settings": ["0x404e9b5c"],
         "memory": [{"va": f"{va:#x}", "size": SIZE[va]} for va in own] + [{"va": f"{DSTATE:#x}", "size": 20, "ram": True}],
         "symbols": {"D": f"{D['d']:#x}", "W": f"{D['w']:#x}", "NX": f"{D['nx_addr']:#x}", "loop": f"{M_DL:#x}",
                     "R": f"{lab['R']:#x}", "N": f"{lab['N']:#x}", "H": f"{lab['H']:#x}"},
         "char": CHAR, "loud": LOUD, "writes": w}
    return t, (D, parts, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (D, parts, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print({k: len(v) for k, v in D.items() if isinstance(v, bytes)}, t["symbols"], "geaendert:", t["changes"])
