#!/usr/bin/env python3
"""Mod 'load-meter' (v2): Lastanzeige der Audio-Berechnung. Braucht nur 'core'. Nach dem Einschalten aus
(an nur, wenn METER = 'LDON'; der RAM hinter dem BSS wird beim Start nicht geloescht).
SETTINGS halten + REVERB SEND rechts = Kaestchen 'LOAD Spitze/Mittel' (% der Blockzeit, alle 0.5 s), links = aus.
Messung wie v1 (gen_loadmeter_113): PROBE statt jsr Audio bei 0x40059382; Spitze% = (Ticks*1164)>>20,
  Mittel% = ((Summe>>10)*1589)>>20 ueber 750 Bloecke. Anzeige jetzt ueber Core-OVS (Art 3, eigene Zeichenfunktion LDRAW
  mit der 3x7-Schrift aus v1, nur noch die noetigen Zeichen).
LMH (Core-Slot 3): SETTINGS + REVERB SEND.
Speicher: 0x4016b6f8 (PROBE, NUM), 0x4016b9e8 (LDRAW, Schrift), 0x40152d38 (LMH). RAM 0x4a33c3d0..0x4a33c3f3 (36 B).
Aufruf: g2_loadmeter.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_overlay_113 as ovl

M_LM, M_LM2, M_LM3 = 0x4016B6F8, 0x4016B9E8, 0x40152D38
SIZES = {M_LM: 376, M_LM2: 376, M_LM3: 192}
P_HOOK, P_ORIG, AUDIO = 0x40059382, (6, 'bc2910c59a0d8e6999ccd601395bca9fd72e3e23d992899f38377b3b07ac2f81'), 0x4005979E   # jsr AUDIO (Laenge + SHA-256)
MV = 0x4A33C3D0
METER, PR_RET, PR_T0, PK, SUM, N, BUFN, BUF = 0, 4, 8, 12, 16, 20, 24, 28
LM_ON = 0x4C444F4E                    # 'LDON': an nur mit diesem Wort (RAM nach dem Einschalten zufaellig -> sonst aus)
NBLK, K_PK, K_AVG = 750, 1164, 1589
ORDER = "0123456789-/LOAD"
DASH, SLASH = ORDER.index('-'), ORDER.index('/')
BOX = (28, 18, 99, 47)
LABEL, LABEL_X = "LOAD", 56


def build_probe(ldraw):
    cs = core.sym()
    a = A(M_LM); w, l = a.w, a.l32
    a.label('PROBE')
    w(0x2039); l(MV + METER); w(0x0C80); l(LM_ON); a.bcc(EQ, 'pm')   # move.l METER,d0 ; cmpi.l #LDON,d0
    w(0x4EF9); l(AUDIO)
    a.label('pm')
    w(0x23DF); l(MV + PR_RET)
    w(0x2039); l(C.TIMER); w(0x23C0); l(MV + PR_T0)
    a.orig(P_HOOK, 6)                           # verschobener Originalbefehl: jsr AUDIO
    w(0x2F00)
    w(0x2039); l(C.TIMER); w(0x90B9); l(MV + PR_T0)
    w(0x41F9); l(MV)
    w(0xB0A8, PK); a.bcc(LS, 'p1'); w(0x2140, PK)
    a.label('p1')
    w(0xD1A8, SUM, 0x52A8, N)
    w(0x2028, N, 0x0C80); l(NBLK); a.bcc(CS, 'pout')
    w(0x4FEF, 0xFFF0, 0x48D7, 0x041C)
    w(0x2228, PK, 0x243C); l(K_PK); w(0x4C02, 0x1800, 0x7414, 0xE4A9)
    w(0x2628, SUM, 0x740A, 0xE4AB, 0x243C); l(K_AVG); w(0x4C02, 0x3800, 0x7414, 0xE4AB)
    w(0x42A8, PK, 0x42A8, SUM, 0x42A8, N)
    w(0x45F9); l(MV + BUF); w(0x7800)
    w(0x2F03, 0x2001); a.bcc(BSR, 'NUM')
    w(0x7000 | SLASH, 0x14C0, 0x5284)
    w(0x201F); a.bcc(BSR, 'NUM')
    w(0x23C4); l(MV + BUFN)
    w(0x7000 | C.OV_CUSTOM, 0x41F9); l(ldraw); w(0x93C9, 0x4EB9); l(cs['OVS'])   # OVS(3, -, LDRAW, 0)
    w(0x4CD7, 0x041C, 0x4FEF, 0x0010)
    a.label('pout')
    w(0x201F, 0x2F39); l(MV + PR_RET); w(0x4E75)
    a.label('NUM')
    w(0x0C80); l(999); a.bcc(LS, 'n0'); w(0x203C); l(999)
    a.label('n0')
    w(0x7600, 0x7264); a.bcc(BSR, 'DIG')
    w(0x720A); a.bcc(BSR, 'DIG')
    w(0x7601, 0x7201); a.bcc(BSR, 'DIG')
    w(0x4E75)
    a.label('DIG')
    w(0x7400)
    a.label('dl'); w(0xB081); a.bcc(CS, 'dd'); w(0x9081, 0x5282); a.bcc(BRA, 'dl')
    a.label('dd'); w(0x4A82); a.bcc(NE, 'pr'); w(0x4A83); a.bcc(EQ, 'dr')
    a.label('pr'); w(0x14C2, 0x5284, 0x7601)
    a.label('dr'); w(0x4E75)
    code = a.done(); check_cf(code, M_LM)
    return code, dict(a.lab)


def build_lmh(ldraw):
    cs = core.sym()
    a = A(M_LM3); w, l = a.w, a.l32
    # ---------------- LMH (Core-Slot): SETTINGS + REVERB SEND
    a.label('LMH')
    w(0x202A, 0x0004, 0x0C80); l(C.ENC_RSEND); a.bcc(NE, 'no')
    w(0x712A, 0x0008); a.bcc(EQ, 'no')
    w(0x4878, C.KEY_SET, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'no')
    w(0x7000 | C.KEY_SET, 0x4EB9); l(cs['GEST'])
    w(0x712A, 0x0008); a.bcc(MI, 'off')
    w(0x42B9); l(MV + PK); w(0x42B9); l(MV + SUM); w(0x42B9); l(MV + N)
    w(0x203C); l(LM_ON); w(0x23C0); l(MV + METER)
    w(0x7000 | DASH, 0x13C0); l(MV + BUF); w(0x13C0); l(MV + BUF + 1)
    w(0x7002, 0x23C0); l(MV + BUFN)
    w(0x7000 | C.OV_CUSTOM, 0x41F9); l(ldraw)
    w(0x93C9, 0x4EB9); l(cs['OVS']); a.bcc(BRA, 'sk')
    a.label('off')
    w(0x42B9); l(MV + METER)
    w(0x7000 | C.OV_HIDE, 0x4EB9); l(cs['OVS'])
    a.label('sk'); w(0x7001, 0x4E75)
    a.label('no'); w(0x7000, 0x4E75)
    code = a.done(); check_cf(code, M_LM3)
    return code, dict(a.lab)


def build_ui():
    a = A(M_LM2); w, l = a.w, a.l32
    # ---------------- LDRAW (a2 Bitmap): Kaestchen, 'LOAD', Wert (wie v1 gen_overlay_113 Art 3)
    def fill(x0, y0, x1, y1, col):
        w(0x7400 | x0, 0x7600 | y0, 0x7800 | x1, 0x7A00 | y1, 0x7C00 | col); a.bcc(BSR, 'RECT')
    a.label('LDRAW')
    x0, y0, x1, y1 = BOX
    fill(x0, y0, x1, y1, 0)
    fill(x0, y1, x1, y1, 1); fill(x0, y0, x1, y0, 1); fill(x0, y0, x0, y1, 1); fill(x1, y0, x1, y1, 1)
    w(0x41F9); l(0); fix_lab = len(a.b) - 4
    w(0x7600 | len(LABEL), 0x7400 | LABEL_X, 0x7E25, 0x7C01); a.bcc(BSR, 'DS')
    w(0x41F9); l(MV + BUF); w(0x2639); l(MV + BUFN)
    w(0x5383, 0x7207, 0xB283); a.bcc(CS, 'ld'); w(0x5283)      # 1..8 Zeichen
    w(0x7441, 0x2003, 0xE588, 0x9480, 0x7C02, 0x7E15); a.bcc(BSR, 'DS')
    a.label('ld'); w(0x4E75)
    # DS: a0 Zeichen, d3 Anzahl, d2 x, d7 y unten, d6 Massstab
    a.label('DS')
    w(0x7000, 0x1018, 0x2F08, 0xE588, 0x43F9); l(0); fix_f = len(a.b) - 4
    w(0x2A31, 0x0800); a.bcc(BSR, 'GL')
    w(0x205F, 0x2006, 0xE588, 0xD480, 0x5383); a.bcc(NE, 'DS')
    w(0x4E75)
    a.label('GL')
    w(0x2F03, 0x2807, 0x7607)
    a.label('gr')
    w(0x0805, 0x0002); a.bcc(EQ, 'c1'); w(0x2002); a.bcc(BSR, 'BLK')
    a.label('c1')
    w(0x0805, 0x0001); a.bcc(EQ, 'c2'); w(0x2002, 0xD086); a.bcc(BSR, 'BLK')
    a.label('c2')
    w(0x0805, 0x0000); a.bcc(EQ, 'c3'); w(0x2002, 0xD086, 0xD086); a.bcc(BSR, 'BLK')
    a.label('c3')
    w(0xE68D, 0xD886, 0x5383); a.bcc(NE, 'gr')
    w(0x261F, 0x4E75)
    a.label('RECT')
    w(0x2F06, 0x2F05, 0x2F04, 0x2F03, 0x2F02, 0x2F0A, 0x4EB9); l(ovl.FILL); w(0x4FEF, 0x0018, 0x4E75)
    a.label('BLK')
    w(0x4878, 0x0001)
    w(0x2204, 0xD286, 0x5381, 0x2F01)
    w(0x2200, 0xD286, 0x5381, 0x2F01)
    w(0x2F04, 0x2F00, 0x2F0A, 0x4EB9); l(ovl.FILL); w(0x4FEF, 0x0018, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_LM2)
    while len(code) % 4: code += b'\0'
    font_at = M_LM2 + len(code)
    code += struct.pack('>%dI' % len(ORDER), *[ovl.glyph(c) for c in ORDER])
    lab_at = M_LM2 + len(code); code += bytes(ORDER.index(c) for c in LABEL)
    code[fix_f:fix_f + 4] = struct.pack('>I', font_at)
    code[fix_lab:fix_lab + 4] = struct.pack('>I', lab_at)
    return bytes(code), dict(a.lab, FONT=font_at)


def build():
    ui, lu = build_ui()
    pr, lp = build_probe(lu['LDRAW'])
    lh, ll = build_lmh(lu['LDRAW'])
    lu.update(lp); lu.update(ll)
    return {M_LM: pr, M_LM2: ui, M_LM3: lh}, lu


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZES[va])
    W.hook(P_HOOK, P_ORIG, jsr(lab['PROBE']))
    core.slot_write(W, 'load-meter', lab['LMH'])
    return patch('load-meter', 8, 'Audio load meter',
                 ["SETTINGS + REVERB SEND right = 'LOAD peak/average' (percent of the audio block time, every 0.5 s), left = off.",
                  "Off after power-on. Erzeugt von v2/g2_loadmeter.py."], W, requires=['core'],
                 hooks=[f"{P_HOOK:#x}"],
                 memory=[{"va": f"{MV:#x}", "size": 36, "ram": True, "use": "meter state + text"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('PROBE', 'NUM', 'LMH', 'LDRAW', 'FONT')},
                 params={"slot": C.SLOT['load-meter'], "mv": f"{MV:#x}", "nblk": NBLK, "k_pk": K_PK, "k_avg": K_AVG,
                         "block_ticks": 90112})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
