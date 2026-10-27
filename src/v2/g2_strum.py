#!/usr/bin/env python3
"""Mod 'strum' (v2): STRUM fuer die CHORD-Maschine. Braucht nur 'core'.
SETTINGS halten + SHAPE drehen: -80..80 (Popup 'Strum'), Wert = ms zwischen zwei Akkordtoenen; rechts tief -> hoch,
  links hoch -> tief, 0 = alle gleichzeitig. Gespeichert im Pattern: Kopf-Byte 56 (vorzeichenbehaftet; ausserhalb = 0).
Klang wie v1 (gen_strum_113): Haken ST am Ende des CHORD-Updates 0x400ab240 (jmp, Epilog nachgespielt), G0F im Render
  0x400ab2d2; ST liest STRUM jetzt aus dem Kopf des laufenden Patterns statt aus dem Einstellungsblock.
STH (Core-Slot 2): SETTINGS + SHAPE.
Speicher: 0x40192734 (ST, G0F), 0x4018d4a8 (STH + Text). RAM: Zaehler 0x4233c360 (24 B), G0 0x4233c378.
Aufruf: g2_strum.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_strum_113 as st

M_ST, M_STH, SIZE = st.M_ST, st.M_SP2, 376
CNT, G0, G0_FULL = st.CNT, st.G0, st.G0_FULL
VOICE0, VSTEP, NVOICE, K_SP, SMAX = st.VOICE0, st.VSTEP, st.NVOICE, st.K_SP, st.SMAX
ST_HOOK, ST_ORIG, R_HOOK, R_ORIG = st.ST_HOOK, st.ST_ORIG, st.R_HOOK, st.R_ORIG


def build_st():
    """Wie gen_strum_113.build (ST + G0F), STRUM aus dem Pattern-Kopf (a1 frei an dieser Stelle)."""
    a = A(M_ST); w, l = a.w, a.l32
    a.label('ST')
    w(0x200A, 0x0480); l(VOICE0)
    a.bcc(MI, 'full')
    w(0x0C80); l(NVOICE * VSTEP); a.bcc(CC, 'full')
    w(0x7200)
    a.label('vi')
    w(0x0C80); l(VSTEP); a.bcc(CS, 'vf')
    w(0x0480); l(VSTEP); w(0x5281); a.bcc(BRA, 'vi')
    a.label('vf')
    w(0x4A80); a.bcc(NE, 'full')
    w(0x7006, 0xB081); a.bcc(LS, 'full')
    w(0xE589, 0x41F9); l(CNT); w(0xD1C1)
    w(0x4AAA, 0x0038); a.bcc(EQ, 'inc')
    w(0x4290); a.bcc(BRA, 'gate')
    a.label('inc')
    w(0x2010, 0x0C80); l(0xFFFF); a.bcc(CC, 'gate')
    w(0x5290)
    a.label('gate')
    w(0x2039); l(C.CUR_PAT); a.bcc(EQ, 'sv')          # move.l CUR_PAT,d0 ; beq (d0 = 0)
    w(0x2240, 0x7129, C.HDR + C.P_STRUM)              # movea.l d0,a1 ; mvs.b HDR+56(a1),d0
    a.label('sv')
    w(0x0C80); l(SMAX); a.bcc(GT, 'bad')
    w(0x0C80); l(-SMAX & 0xFFFFFFFF); a.bcc(GE, 'sok')
    a.label('bad'); w(0x7000)
    a.label('sok')
    w(0x7A00, 0x4A80); a.bcc(PL, 'up'); w(0x4480, 0x7A01)
    a.label('up')
    w(0x7200 | K_SP, 0x4C00, 0x1800, 0xEC89)
    a.bcc(EQ, 'full')
    w(0x2010, 0x43EA, 0x000C, 0x7601)
    a.label('kl')
    w(0x2403, 0x4A85); a.bcc(EQ, 'su'); w(0x7403, 0x9483)
    a.label('su')
    w(0x4C01, 0x2800)
    w(0x2800, 0x9882); a.bcc(MI, 'zero')
    a.bcc(EQ, 'quart')
    w(0x0C84); l(1); a.bcc(EQ, 'half')
    a.bcc(BRA, 'nk')
    a.label('zero'); w(0x4291); a.bcc(BRA, 'nk')
    a.label('quart'); w(0x2811, 0xE484, 0x2284); a.bcc(BRA, 'nk')
    a.label('half'); w(0x2811, 0xE284, 0x2284)
    a.label('nk')
    w(0x5889, 0x5283, 0x0C83); l(4); a.bcc(NE, 'kl')
    w(0x7400, 0x4A85); a.bcc(EQ, 'o0'); w(0x2401, 0xD481, 0xD481)
    a.label('o0')
    w(0x2800, 0x9882); a.bcc(MI, 'g0z')
    w(0x0C84); l(7); a.bcc(GT, 'full')
    w(0x5284, 0x741A, 0xE5AC, 0x23C4); l(G0); a.bcc(BRA, 'out')
    a.label('g0z'); w(0x42B9); l(G0); a.bcc(BRA, 'out')
    a.label('full'); w(0x283C); l(G0_FULL); w(0x23C4); l(G0)
    a.label('out')
    a.orig(ST_HOOK, 12)                         # Epilog des CHORD-Updates (verschoben, aus dem Image)
    a.label('G0F'); w(0x2239); l(G0); w(0x4E75)
    code = a.done(); check_cf(code, M_ST)
    return code, dict(a.lab)


def build_sth():
    cs = core.sym()
    a = A(M_STH); w, l = a.w, a.l32
    a.label('STH')
    w(0x202A, 0x0004, 0x0C80); l(C.ENC_SHAPE); a.bcc(NE, 'no')
    w(0x712A, 0x0008); a.bcc(EQ, 'no')
    w(0x4878, C.KEY_SET, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'no')
    w(0x7000 | C.KEY_SET, 0x4EB9); l(cs['GEST'])
    w(0x2039); l(C.CUR_PAT); a.bcc(EQ, 'sk')
    w(0x2040, 0x41E8, C.HDR + C.P_STRUM)       # a0 = &STRUM
    w(0x7110)                                  # mvs.b (a0),d0
    w(0x0C80); l(SMAX); a.bcc(GT, 'tz')
    w(0x0C80); l(-SMAX & 0xFFFFFFFF); a.bcc(GE, 'tv')
    a.label('tz'); w(0x7000)
    a.label('tv')
    w(0x732A, 0x0008, 0xD081)
    w(0x0C80); l(SMAX); a.bcc(LE, 't1'); w(0x7000 | SMAX)
    a.label('t1')
    w(0x0C80); l(-SMAX & 0xFFFFFFFF); a.bcc(GE, 't2'); w(0x7000 | (-SMAX & 0xFF))
    a.label('t2')
    w(0x1080, 0x2200)                          # move.b d0,(a0) ; move.l d0,d1
    w(0x41F9); l(0); fix = len(a.b) - 4        # lea 'Strum',a0
    w(0x93C9, 0x7000 | C.OV_NUM, 0x4EB9); l(cs['OVS'])
    a.label('sk'); w(0x7001, 0x4E75)
    a.label('no'); w(0x7000, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_STH)
    s_at = M_STH + len(code); code += b"Strum\0"
    code[fix:fix + 4] = struct.pack('>I', s_at)
    return bytes(code), dict(a.lab)


def build():
    c1, l1 = build_st(); c2, l2 = build_sth()
    l1.update(l2)
    return {M_ST: c1, M_STH: c2}, l1


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE)
    W.hook(ST_HOOK, ST_ORIG, jmp(lab['ST']))
    W.hook(R_HOOK, R_ORIG, jsr(lab['G0F']))
    core.slot_write(W, 'strum', lab['STH'])
    return patch('strum', 7, 'Strum for the CHORD machine',
                 ["SETTINGS + SHAPE: -80..80 = ms between chord notes (right up, left down). Stored per pattern (header byte 56).",
                  "Erzeugt von v2/g2_strum.py."], W, requires=['core'],
                 hooks=[f"{ST_HOOK:#x}", f"{R_HOOK:#x}"],
                 memory=[{"va": f"{CNT:#x}", "size": 24, "ram": True, "use": "voice counters"},
                         {"va": f"{G0:#x}", "size": 4, "ram": True, "use": "root note level"}],
                 pattern=f"header byte {C.P_STRUM}: strum, signed -80..80",
                 symbols={k: f"{lab[k]:#x}" for k in ('ST', 'G0F', 'STH')},
                 params={"slot": C.SLOT['strum'], "k": K_SP, "smax": SMAX, "cnt": f"{CNT:#x}", "g0": f"{G0:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
