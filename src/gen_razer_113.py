#!/usr/bin/env python3
"""Tweak 'razer' fuer die OFFIZIELLE Model:Cycles OS 1.13: RAZR, Reverb-Platz Modus 4 (Idee: JHS 3 Series Pherb).
Setzt delay-notes, chorus, phaser, digi-delay voraus (erweitert deren gemeinsame Umschaltung/Namen/H4).
  TRACK + Reverb Size: Reverb -> Chorus I -> Chorus II -> Phaser -> RAZR.
  Reverb Send = Mix, Reverb Size = Length (Laenge des Elektron-Reverbs), Reverb Tone = Speed (0.05..5 Hz, 0 = Phaser aus).
Signalweg je Block (32 Frames):
  1. Elektron-Reverb 0x400579c4 mit eigenem Parameterblock: Size = Length, Tone fest dunkel (TONE)
  2. Lo-Fi: Sample-and-Hold x2 auf dem Reverb (halbe Abtastrate) und x3 mit Saettigung (GAIN), wirkt auch bei Speed 0
  3. Speed > 0: 4-stufiger Phaser wie Modus 3 (gleicher Durchlauf 0x4018ff64), leichtes Feedback (FB), Stufen FMIN..FMAX
     (Notches hoeher als im Phaser-Modus, im Klangbereich des dunklen Reverbs). v2 (25.10.2026) nach Pips Test: lauter, mehr Tiefe. Pegel bei Rauschen etwa wie das Reverb allein (-1 dB, Test).
     Stereo: Phaser auf der Mono-Summe, rechts gegenphasiger LFO.
Speicher: Maske 0x4016cae8 (64x128, 1024 B: Code, Koeffizienten + Tabelle, Namen) | RAM: Phaser-Zustand 0x4a33c180..+0x38,
  Parameterblock 0x4a33c200 (4 B), Zwischenpuffer 0x4a33c210..+0x100.
Aufruf: gen_razer_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE
from gen_chorusfx import check_cf
import gen_fx4 as fx
import gen_chorus_113 as ch
import gen_phaser_113 as ph
import gen_digidelay_113 as dd
import gen_delaynotes_113 as dn

M_RZ, SIZE = 0x4016CAE8, 1024
PSTATE2, RZP, TMP = 0x4233C180, 0x4233C200, 0x4233C210   # gecachte Aliase von 0x4a33c180.. (v2 ungecacht)
TONE = 32                      # fester Reverb-Ton (0..127, < 64 = dunkel); v1: 20 (zu leise/zu dunkel fuer den Phaser)
FMIN, FMAX = 180.0, 3600.0     # Phaser-Stufen (Modus 3: 100 .. 4000 Hz); v1: 250 .. 5000 (Notches ueber dem Reverb-Klang)
GAIN = 3                       # Reverb x3 (+9.5 dB) mit Saettigung, vor Phaser und Speed-0-Pfad; v1: x1
FB = 9830                      # Phaser-Feedback Q15 (0.30, etwa Color 50 im Phaser-Modus); v1: 0
SPD_K, SPD_0 = 27, 4474        # Phasenzuwachs je Block = (S*S*SPD_K + SPD_0) << 5  -> 0.05 .. 4.97 Hz
REVERB = 0x400579C4
ROW = (b"Razr Mix", b"RAZR", b"Razr Length", b"LEN", b"Razr Speed", b"SPD")
NE, EQ, PL = 0x6, 0x7, 0xA


def build_rz(pass_at, coef_at):
    a = A(M_RZ); w, l = a.w, a.l32
    a.label('RZ')                            # Stack: ret, out, in, params
    w(0x4FEF, 0xFFD4, 0x48D7, 0x7CFC)        # lea -44(a7),a7 ; movem.l d2-d7/a2-a6,(a7)  -> out 48, in 52, params 56
    w(0x206F, 0x0038)                        # movea.l 56(a7),a0      params
    w(0x43F9); l(RZP)                        # lea RZP,a1
    w(0x3290)                                # move.w (a0),(a1)       Size = Length
    w(0x223C); l(TONE << 8); w(0x3341, 0x0002)   # move.l #TONE,d1 ; move.w d1,2(a1)   Tone fest
    w(0x4851, 0x2F2F, 0x0038, 0x2F2F, 0x0038)    # pea (a1) ; in ; out
    w(0x4EB9); l(REVERB); w(0x4FEF, 0x000C)  # jsr Reverb ; lea 12(a7),a7
    # Lo-Fi: Sample-and-Hold x2 (ungerade Frames = vorheriger Frame)
    w(0x206F, 0x0030, 0x700F)                # movea.l 48(a7),a0 ; moveq #15,d0
    a.label('sh')
    w(0x2210, 0x2428, 0x0004)                # move.l (a0),d1 ; move.l 4(a0),d2
    assert GAIN == 3
    w(0x2601, 0xD281, 0x4C81, 0xD283, 0x4C81)    # d1 = sat(sat(2*d1) + d1)   (x3)
    w(0x2602, 0xD482, 0x4C82, 0xD483, 0x4C82)    # d2 ebenso
    w(0x20C1, 0x20C2, 0x20C1, 0x20C2, 0x5380); a.bcc(PL, 'sh')   # Frame n und n+1
    # Speed = Tone-Regler; 0 -> nur Reverb
    w(0x206F, 0x0038, 0x71E8, 0x0002, 0xE088)    # movea.l 56(a7),a0 ; mvz.w 2(a0),d0 ; lsr.l #8,d0
    a.bcc(EQ, 'done')
    # out -> TMP (der Phaser liest beide Kanaele, schreibt aber kanalweise nach out)
    w(0x206F, 0x0030, 0x43F9); l(TMP); w(0x723F)  # movea.l 48(a7),a0 ; lea TMP,a1 ; moveq #63,d1
    a.label('cp')
    w(0x22D8, 0x5381); a.bcc(PL, 'cp')      # move.l (a0)+,(a1)+ ; subq.l #1,d1
    # Phaser-Setup wie fx.build_ps, Speed aus d0, ohne Feedback, eigener Zustand, Eingang TMP
    w(0x2400, 0x4C00, 0x2800, 0x7600 | SPD_K, 0x4C03, 0x2800)   # d2 = S*S*K
    w(0x0682); l(SPD_0); w(0xEB8A)           # + SPD_0 ; lsl.l #5,d2
    w(0x247C); l(FB)                         # movea.l #FB,a2   Feedback
    w(0x47F9); l(PSTATE2)
    w(0x202B, 0x0004, 0x0C80); l(fx.PMAGIC); a.bcc(EQ, 'ok')
    w(0x204B, 0x700B)
    a.label('cl'); w(0x4298, 0x5380); a.bcc(PL, 'cl')
    w(0x203C); l(fx.PMAGIC); w(0x2740, 0x0004)
    a.label('ok')
    w(0x2013, 0xD082, 0x2680)
    w(0x4EB9); l(coef_at); w(0x2747, 0x0030)
    w(0x2013, 0x0680); l(0x80000000)
    w(0x4EB9); l(coef_at); w(0x2747, 0x0034)
    for c, so, sa in ((0, 8, 0x30), (4, 28, 0x34)):
        w(0x41F9); l(TMP)                    # lea TMP,a0   (statt in)
        w(0x226F, 0x0030)                    # movea.l 48(a7),a1   out
        if c: w(0x5889)
        w(0x49E8, 0x0100)
        w(0x2E2B, sa)
        w(0x4CEB, 0x007C, so)
        w(0x4EB9); l(pass_at)
        w(0x48EB, 0x007C, so)
    a.label('done')
    w(0x4CD7, 0x7CFC, 0x4FEF, 0x002C, 0x4E75)
    code = a.done(); check_cf(code, M_RZ)
    return code, a.lab['RZ']


def build_coef2(at):
    old = (fx.M_PT, fx.FMIN, fx.FMAX)
    fx.M_PT, fx.FMIN, fx.FMAX = at, FMIN, FMAX
    try:
        code, coef = fx.build_coef()
    finally:
        fx.M_PT, fx.FMIN, fx.FMAX = old
    return code, coef


def build_razer():
    P, _ = ph.phaser_opts()
    rz0, _ = build_rz(P['p_addr'], 0)                    # Laenge
    coef_at = (M_RZ + len(rz0) + 3) & ~3
    coef, coef_addr = build_coef2(coef_at)
    rz, rz_addr = build_rz(P['p_addr'], coef_addr)
    assert len(rz) == len(rz0)
    str_at = coef_at + len(coef)
    blob = rz + bytes(coef_at - M_RZ - len(rz)) + coef
    return dict(blob=blob, rz=rz_addr, coef=coef_addr, str_at=str_at, pass_at=P['p_addr'])


def tweak(img):
    Z = build_razer()
    D = dd.build(img)
    base = img
    for t0 in (dn.tweak(img)[0], ch.tweak(img)[0], ph.tweak(img)[0], dd.tweak(img)[0]):
        base = dd.apply(base, t0)                        # Stand mit allen Voraussetzungen
    _, popt = ph.phaser_opts()
    ropt = dict(addr=Z['rz'], row=ROW, str_at=Z['str_at'])
    parts, lab, _ = ch.build(img, phaser=popt, nx=D['nx_addr'], extra_entries=[(15, dd.DMODE, 1, [2], 1)], razer=ropt)
    blob = Z['blob'] + ropt['strs']
    assert len(blob) <= SIZE, len(blob)
    sw = lambda va, new: {"off": va - BASE, "old": bytes(base[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = [sw(M_RZ, blob), sprites.redirect_write(M_RZ)]
    changed = []
    for va in (ch.M_UI, ch.M_NAMES, ch.M_H4):
        new = parts[va]
        if bytes(base[va - BASE:va - BASE + len(new)]) != new:
            w.append(sw(va, new)); changed.append(f"{va:#x}")
    w.sort(key=lambda x: x["off"])
    t = {"id": "razer", "order": 69, "name": "RAZR: dunkles Lo-Fi-Reverb in Phaser (Reverb-Platz Modus 4)",
         "description": ["Reverb -> Chorus I -> Chorus II -> Phaser -> RAZR (TRACK + Reverb Size). Mix = Send, Length = Size, Speed = Tone (0 = nur Reverb).",
                         "Idee: JHS 3 Series Pherb. Erzeugt von gen_razer_113.py."],
         "device": "Model:Cycles", "os": "1.13", "section": 3, "requires": ["delay-notes", "chorus", "phaser", "digi-delay"],
         "hooks": [], "changes": changed,
         "memory": [{"va": f"{M_RZ:#x}", "size": SIZE}, {"va": f"{PSTATE2:#x}", "size": 0x38, "ram": True},
                    {"va": f"{RZP:#x}", "size": 4, "ram": True}, {"va": f"{TMP:#x}", "size": 256, "ram": True}],
         "symbols": {"razer": f"{Z['rz']:#x}", "coef": f"{Z['coef']:#x}", "R": f"{lab['R']:#x}", "N": f"{lab['N']:#x}",
                     "H": f"{lab['H']:#x}", "names_str": f"{Z['str_at']:#x}"},
         "params": {"tone": TONE, "fmin": FMIN, "fmax": FMAX, "speed": [SPD_K, SPD_0], "gain": GAIN, "fb": FB},
         "writes": w}
    return t, (Z, parts, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (Z, parts, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("Razer", len(Z['blob']), t["symbols"], "geaendert:", t["changes"])
