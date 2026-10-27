#!/usr/bin/env python3
"""Tweak 'phaser' fuer die OFFIZIELLE Model:Cycles OS 1.13: Phaser als Modus 3 auf dem Reverb-Platz (wie v21).
Setzt den Patch 'chorus' (gen_chorus_113.py) voraus und erweitert dessen Umschaltung:
  TRACK + Reverb Size: Reverb -> Chorus I -> Chorus II -> Phaser. Reverb Size = Speed (0.1..6 Hz), Reverb Tone = Color.

Klang-Code aus v21 (gen_fx4: build_pp, build_coef, build_ps; MXR Phase 90 / Small Stone, 4 Allpass-Stufen):
  Durchlauf und Koeffizienten + Tabelle Byte fuer Byte wie v21 (nur andere Adressen). Das Setup (210 B) passt in keine
  freie Maske am Stueck und ist in zwei Teile geteilt (A ... jmp B), vor den beiden Kanal-Durchlaeufen. Rechenweg gleich.
Masken (in keinem bekannten 1.13-Mod belegt; die 34x34-Masken von lfo-plus sind gemieden):
  Durchlauf + Phaser-Namen 0x4018ff64 (34x34, 272) | Koeffizienten + Tabelle 0x40185648 (46x31, 184)
  Setup A 0x401857f8 (46x31, 184)                   | Setup B 0x4016f7d0 (31x22, 124)
RAM: Phaser-Zustand 0x4a33c100..0x4a33c137 (v21: 0x4a33a200, liegt hier im Chorus-Puffer).
Am Chorus geaendert (old = Bytes des Chorus-Patches): R (Phaser-Abzweig, Namensmaske 3), Namenstabelle (4 Zeilen),
H4 (Maximum 3, Sprungziel N verschoben).
Aufruf: gen_phaser_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE
import gen_fx4 as fx
import gen_chorus_113 as ch
from gen_chorusfx import check_cf

M_PP, M_PT, M_PSA, M_PSB = 0x4018FF64, 0x40185648, 0x401857F8, 0x4016F7D0
SIZE = {M_PP: 272, M_PT: 184, M_PSA: 184, M_PSB: 124}
PSTATE = 0x4233C100                 # gecachter Alias von 0x4a33c100 (v1 ungecacht; nur die CPU greift zu)
ROW = (b"Phas Send", b"PHAS", b"Phas Speed", b"SPD", b"Phas Color", b"COL")
EQ, PL = 0x7, 0xA


def build_ps_split(pass_at, coef_at):
    """fx.build_ps, aufgeteilt: A bis einschliesslich aR, dann jmp B; B = beide Kanal-Durchlaeufe + Epilog."""
    a = A(M_PSA); w, l = a.w, a.l32
    a.label('PH')
    w(0x4FEF, 0xFFD4, 0x48D7, 0x7CFC)
    w(0x206F, 0x0038)
    w(0x71D0, 0xE088, 0x73E8, 0x0002, 0xE089)
    w(0x2400, 0x4C00, 0x2800, 0x7621, 0x4C03, 0x2800)
    w(0x0682); l(8948); w(0xEB8A)
    w(0x263C); l(193); w(0x4C03, 0x1800, 0x2441)
    w(0x47F9); l(PSTATE)
    w(0x202B, 0x0004, 0x0C80); l(fx.PMAGIC); a.bcc(EQ, 'ok')
    w(0x204B, 0x700B)
    a.label('cl'); w(0x4298, 0x5380); a.bcc(PL, 'cl')
    w(0x203C); l(fx.PMAGIC); w(0x2740, 0x0004)
    a.label('ok')
    w(0x2013, 0xD082, 0x2680)
    w(0x4EB9); l(coef_at); w(0x2747, 0x0030)
    w(0x2013, 0x0680); l(0x80000000)
    w(0x4EB9); l(coef_at); w(0x2747, 0x0034)
    w(0x4EF9); l(M_PSB)                     # jmp Teil B
    ca = a.done(); check_cf(ca, M_PSA)
    b = A(M_PSB); w, l = b.w, b.l32
    for c, so, sa in ((0, 8, 0x30), (4, 28, 0x34)):
        w(0x206F, 0x0034, 0x226F, 0x0030)
        if c: w(0x5889)
        w(0x49E8, 0x0100)
        w(0x2E2B, sa)
        w(0x4CEB, 0x007C, so)
        w(0x4EB9); l(pass_at)
        w(0x48EB, 0x007C, so)
    w(0x4CD7, 0x7CFC, 0x4FEF, 0x002C, 0x4E75)
    cb = b.done(); check_cf(cb, M_PSB)
    return ca, cb, a.lab['PH']


def build_phaser():
    fx.M_PP, fx.M_PT, fx.PSTATE = M_PP, M_PT, PSTATE
    pp, p_addr = fx.build_pp()
    pt, coef_addr = fx.build_coef()
    psa, psb, ph = build_ps_split(p_addr, coef_addr)
    return dict(pp=pp, pt=pt, psa=psa, psb=psb, ph=ph, p_addr=p_addr, coef_addr=coef_addr)


def phaser_opts():
    """(Phaser-Teile, Option fuer gen_chorus_113.build) - auch fuer spaetere Patches, die auf dem Phaser aufsetzen."""
    P = build_phaser()
    str_at = (M_PP + len(P['pp']) + 1) & ~1
    return P, dict(addr=P['ph'], row=ROW, str_at=str_at)


def tweak(img):
    P, opt = phaser_opts()
    str_at = opt['str_at']
    # Chorus allein (Zustand, auf dem dieser Patch aufsetzt) und Chorus mit Phaser-Modus
    tc, _ = ch.tweak(img)
    imgc = bytearray(img)
    for x in tc['writes']:
        o = bytes.fromhex(x['old']); assert imgc[x['off']:x['off'] + len(o)] == o
        imgc[x['off']:x['off'] + len(o)] = bytes.fromhex(x['new'])
    parts, lab, pstrs = ch.build(img, phaser=opt)
    ppblob = P['pp'] + bytes(str_at - M_PP - len(P['pp'])) + pstrs
    own = {M_PP: ppblob, M_PT: P['pt'], M_PSA: P['psa'], M_PSB: P['psb']}
    for va, b in own.items():
        assert len(b) <= SIZE[va], (hex(va), len(b), SIZE[va])
    sw = lambda va, new: {"off": va - BASE, "old": bytes(imgc[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = []
    for va, b in own.items():
        w += [sw(va, b), sprites.redirect_write(va)]
    changed = []
    for va in (ch.M_UI, ch.M_NAMES, ch.M_H4):
        new = parts[va]
        old = bytes(imgc[va - BASE:va - BASE + len(new)])
        if new != old:
            w.append(sw(va, new)); changed.append(f"{va:#x}")
    for va, b in parts.items():                     # alles andere vom Chorus muss gleich bleiben
        if va not in (ch.M_UI, ch.M_NAMES, ch.M_H4):
            assert bytes(imgc[va - BASE:va - BASE + len(b)]) == b, hex(va)
    w.sort(key=lambda x: x["off"])
    t = {"id": "phaser", "order": 67, "name": "Phaser auf dem Reverb-Platz (Modus 3, TRACK + Reverb Size)",
         "description": ["Reverb -> Chorus I -> Chorus II -> Phaser. Speed = Reverb Size, Color = Reverb Tone. Phase-90-/Small-Stone-Vorbild.",
                         "Erzeugt von gen_phaser_113.py (Klang-Code wie v21)."],
         "device": "Model:Cycles", "os": "1.13", "section": 3, "requires": ["chorus"],
         "hooks": [], "changes": changed,
         "memory": [{"va": f"{va:#x}", "size": SIZE[va]} for va in own] + [{"va": f"{PSTATE:#x}", "size": 0x38, "ram": True}],
         "symbols": {"phaser": f"{P['ph']:#x}", "pass": f"{P['p_addr']:#x}", "coef": f"{P['coef_addr']:#x}",
                     "R": f"{lab['R']:#x}", "N": f"{lab['N']:#x}", "H": f"{lab['H']:#x}", "names_str": f"{str_at:#x}"},
         "writes": w}
    return t, (P, parts, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (P, parts, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print({k: len(v) for k, v in P.items() if isinstance(v, bytes)}, t["symbols"], "geaendert:", t["changes"])
