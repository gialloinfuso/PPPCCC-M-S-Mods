#!/usr/bin/env python3
"""Mod 'groove' (v2): Grooves + Humanize. Braucht nur 'core'.
FUNC + Swing: Groove (Swing, Boom Bap, Disco, Reggae, Bongo, Caixixi, Highlife, Kuduro; 4 Rastungen je Stufe, Popup
  'Groove' + Name). Swing je Track = Staerke. SETTINGS + Swing = Humanize Zeit, MACHINE + Swing = Humanize Velocity
  (0..100, ausgewaehlter Track; mit TRACK alle Tracks: relativ, oder absolut wenn control-mode es so eingestellt hat).
  MACHINE oeffnet sein Menue beim Loslassen.
Gespeichert im Pattern: Kopf-Byte 55 = Groove (0..7, ungueltig = 0), 40..45 / 46..51 = Humanize Zeit / Velocity
  (Kopieren beim Laden und Loeschen fuer neue Patterns macht der Core).
Klang wie v1 (gen_groove_113): Haken G im Ereignisbau 0x40054af8; G liest den Groove jetzt aus dem Pattern-Kopf (a3 = B).
GRH (Core-Slot 4): FUNC / SETTINGS / MACHINE + Swing. MK (Haken 0x4001ca1e): MACHINE-Menue beim Loslassen.
Speicher: 0x4014b85c (G + Humanize), 0x4014d74c (RND + HUM), 0x401542f8 / 0x401548b4 / 0x4015b8f8 / 0x4016f8c8 (T + Tabellen),
  0x40171f30 (GRH, MK), 0x4015f38c (Texte). RAM: MPEND = VARS+36.
Aufruf: g2_groove.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_groove_113 as gg

HOOK, BACK, ORIG = gg.HOOK, gg.BACK, gg.ORIG
M_G, M_GD, M_T, M_T2, M_T3, M_T4, M_K = gg.M_G, gg.M_GD, gg.M_T, gg.M_T2, gg.M_T3, gg.M_T4, gg.M_K
M_TX = 0x4015F38C                             # Texte (48x22, 192 B)
SIZE = dict(gg.SIZE); SIZE[M_TX] = 192
GMAX, HMAX, HK = gg.GMAX, gg.HMAX, gg.HK
GROOVES = gg.GROOVES
NAMES = ["Swing", "Boom Bap", "Disco", "Reggae", "Bongo", "Caixixi", "Highlife", "Kuduro"]
MPEND = C.VARS + C.V_MPEND
M_HOOK, M_ORIG = gg.M_HOOK, gg.M_ORIG
HDR, HOFF, HOFF_V = C.HDR, C.P_HUM_T, C.P_HUM_V - C.P_HUM_T
assert (HDR, HOFF, HOFF_V) == (gg.HDR, gg.HOFF, gg.HOFF_V)
TXT = {'groove': "Groove", 'humt': "Hum Time", 'humv': "Hum Vel", 'track': "Track", 'all': "All"}


def build_g(t_addr, rnd):
    """wie gen_groove_113.build_g2, Groove aus dem Pattern-Kopf (move.b HDR+55(a3),d7 statt move.b GMODE,d7)."""
    a = A(M_G); w, l = a.w, a.l32
    a.label('G')
    w(0x7E00, 0x1E2B, HDR + C.P_GROOVE)        # moveq #0,d7 ; move.b HDR+55(a3),d7
    w(0x4A87); a.bcc(NE, 'g1')
    a.orig(HOOK, 6); a.bcc(EQ, 'HUM')           # Original-Swing: verschobene Befehle (aus dem Image)
    a.orig(HOOK + 8, 12)
    a.bcc(BRA, 'HUM')
    a.label('g1')
    w(0x0C87); l(GMAX); a.bcc(HI, 'HUM')
    w(0x4EF9); l(t_addr)
    a.label('HUM')
    w(0x7E05, 0xBE86); a.bcc(CS, 'ret')
    w(0x41EB, HDR + HOFF)
    w(0x7000, 0x1030, 0x6800)
    w(0x7200, 0x1230, 0x6800 | HOFF_V)
    w(0x0C80); l(HMAX); a.bcc(LS, 'a1'); w(0x7000)
    a.label('a1')
    w(0x0C81); l(HMAX); a.bcc(LS, 'a2'); w(0x7200)
    a.label('a2')
    w(0x7E00 | HK, 0x4C07, 0x0800, 0xEE80)
    w(0x4C07, 0x1800, 0xEE81)
    w(0x2041)
    w(0x2E00, 0x8E81); a.bcc(EQ, 'ret')
    w(0x732F, 0x003E)
    a.orig(HOOK + 10, 8)                        # Faktor*12*st (Rechnung der Firmware, aus dem Image)
    w(0x2E39); l(rnd)
    w(0x203C); l(1664525)
    w(0x4C00, 0x7800)
    w(0x0687); l(1013904223)
    w(0x23C7); l(rnd)
    w(0x2007, 0x4840)
    w(0x0280); l(0x7FFF)
    w(0x0480); l(0x4000)
    w(0x4C01, 0x0800)
    w(0xE080, 0xE080, 0xE280)
    w(0xDA80)
    w(0x2007, 0xE288)
    w(0x0280); l(0x7FFF)
    w(0x0480); l(0x4000)
    w(0x2208)
    w(0x4C01, 0x0800)
    w(0x222F, 0x0034)
    w(0x4A81); a.bcc(LE, 'ret')
    w(0x4C01, 0x0800)
    w(0x2E00, 0xE588, 0xD087)
    w(0x0680); l(0x800000)
    w(0x7E18, 0xEEA0)
    w(0xD280, 0x7001, 0xB081); a.bcc(LE, 'v1'); w(0x2200)
    a.label('v1')
    w(0x707F, 0xB081); a.bcc(GE, 'v2'); w(0x2200)
    a.label('v2')
    w(0x2F41, 0x0034)
    a.label('ret')
    w(0x4E75)
    code = a.done(); check_cf(code, M_G); assert len(code) <= SIZE[M_G], len(code)
    return code, dict(a.lab)


def build_hum(org, txt):
    """HUM (d0 = 0 Zeit / 6 Velocity; a2 = Ereignis) -> d0 = 1."""
    cs = core.sym()
    a = A(org); w, l = a.w, a.l32
    a.label('HUM')
    w(0x4FEF, 0xFFEC, 0x48D7, 0x043C)           # lea -20(a7),a7 ; movem.l d2-d5/a2,(a7)
    w(0x2A00, 0x7000 | C.KEY_SET, 0x4A85); a.bcc(EQ, 'k1'); w(0x7000 | C.KEY_MACH)
    a.label('k1')
    w(0x4EB9); l(cs['GEST']); w(0x42B9); l(MPEND)
    w(0x772A, 0x0008)                           # mvs.b 8(a2),d3
    w(0x4878, C.KEY_TRACK, 0x4EB9); l(C.HELD); w(0x588F, 0x2800)
    w(0x4EB9); l(C.SEL_A); w(0x2F00, 0x4EB9); l(C.SEL_B); w(0x2F00, 0x4EB9); l(C.SEL_C); w(0x508F)
    w(0x7205, 0xB280); a.bcc(CS, 'hx')
    w(0x2400)
    w(0x2479); l(C.CUR_PAT); w(0x220A); a.bcc(EQ, 'hx')
    w(0x45EA, HDR + HOFF, 0xD5C5)
    w(0x7200)
    a.label('lp')
    w(0x4A84); a.bcc(NE, 'do')
    w(0xB282); a.bcc(NE, 'nt')
    a.label('do')
    w(0x7000, 0x1032, 0x1800)
    w(0x0C80); l(HMAX); a.bcc(LS, 'h0'); w(0x7000)
    a.label('h0')
    w(0xD083); a.bcc(PL, 'h1'); w(0x7000)
    a.label('h1')
    w(0x0C80); l(HMAX); a.bcc(LE, 'h2'); w(0x7000 | HMAX)
    a.label('h2')
    w(0x1580, 0x1800)
    a.label('nt')
    w(0x5281, 0x7006, 0xB081); a.bcc(NE, 'lp')
    w(0x7200, 0x1232, 0x2800)                   # d1 = Wert des ausgewaehlten Tracks
    # CONTROL ALL absolut (Byte des Cores, von control-mode gesetzt): alle Tracks = neuer Wert des ausgewaehlten
    w(0x4A84); a.bcc(EQ, 'ab')
    w(0x71B9); l(C.CTRL_MODE); w(0x0C80); l(C.CTRL_ABS); a.bcc(NE, 'ab')   # mvz.b CTRL_MODE,d0 ; cmpi.l #ABS,d0
    w(0x7005)
    a.label('cp')
    w(0x1581, 0x0800, 0x5380); a.bcc(PL, 'cp')  # move.b d1,(0,a2,d0.l) ; subq.l #1,d0 ; bpl
    a.label('ab')
    w(0x41F9); l(txt['humt']); w(0x4A85); a.bcc(EQ, 's1'); w(0x41F9); l(txt['humv'])
    a.label('s1')
    w(0x43F9); l(txt['track']); w(0x4A84); a.bcc(EQ, 's2'); w(0x43F9); l(txt['all'])
    a.label('s2')
    w(0x7000 | C.OV_NUM, 0x4EB9); l(cs['OVS'])
    a.label('hx')
    w(0x4CD7, 0x043C, 0x4FEF, 0x0014, 0x7001, 0x4E75)
    code = a.done(); check_cf(code, org)
    return code, dict(a.lab)


def build_k(hum, txt, gnames):
    """GRH (Core-Slot) + MK + Texte in M_K."""
    cs = core.sym()
    a = A(M_K); w, l = a.w, a.l32
    a.label('GRH')
    w(0x202A, 0x0004, 0x0C80); l(C.ENC_SWING); a.bcc(NE, 'no')
    w(0x712A, 0x0008); a.bcc(EQ, 'no')
    w(0x4878, C.KEY_SET, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'nf')
    w(0x7000, 0x4EF9); l(hum)                   # SETTINGS: Humanize Zeit
    a.label('nf')
    w(0x4878, C.KEY_MACH, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'nm')
    w(0x7000 | HOFF_V, 0x4EF9); l(hum)         # MACHINE: Humanize Velocity
    a.label('nm')
    w(0x4878, C.KEY_FUNC, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(NE, 'grv')
    a.label('no'); w(0x7000, 0x4E75)
    # ---- FUNC + Swing: Groove (Pattern-Byte 55)
    a.label('grv')
    w(0x4FEF, 0xFFF8, 0x48D7, 0x0030)           # lea -8(a7),a7 ; movem.l d4-d5,(a7)
    w(0x792A, 0x0008)                           # mvs.b 8(a2),d4
    w(0x2A39); l(C.CUR_PAT); a.bcc(EQ, 'gsk')   # move.l CUR_PAT,d5 ; beq
    w(0x0685); l(HDR + C.P_GROOVE)              # addi.l #HDR+55,d5   (auch Ziel-Kennung fuer SLOW)
    w(0x4EB9); l(cs['SLOW']); w(0x4A80); a.bcc(EQ, 'gsk')
    w(0x2045, 0x7190)                           # movea.l d5,a0 ; mvz.b (a0),d0
    w(0x0C80); l(GMAX); a.bcc(LS, 'g0'); w(0x7000)
    a.label('g0')
    w(0x4A84); a.bcc(MI, 'gdn')
    w(0x0C80); l(GMAX); a.bcc(EQ, 'gsh'); w(0x5280); a.bcc(BRA, 'gst')
    a.label('gdn')
    w(0x4A80); a.bcc(EQ, 'gsh'); w(0x5380)
    a.label('gst')
    w(0x1080)                                   # move.b d0,(a0)
    a.label('gsh')
    w(0xE588, 0x43F9); l(gnames); w(0x2231, 0x0800)   # d1 = Name[Groove]
    w(0x41F9); l(txt['groove']); w(0x93C9, 0x7000 | C.OV_TEXT, 0x4EB9); l(cs['OVS'])
    a.label('gsk')
    w(0x4CD7, 0x0030, 0x4FEF, 0x0008, 0x7001, 0x4E75)
    # ---- MK: MACHINE im Hauptbildschirm (wie v1)
    a.label('MK')
    w(0x2043, 0x2028, 0x0010, 0x7209, 0xC081, 0x5380); a.bcc(NE, 'mr')
    w(0x7001, 0x23C0); l(MPEND); w(0x588F, 0x4EF9); l(core.K_DONE)
    a.label('mr')
    w(0x2028, 0x0010, 0x0800, 0x0004); a.bcc(EQ, 'mn')
    w(0x4AB9); l(MPEND); a.bcc(EQ, 'mn')
    w(0x42B9); l(MPEND); w(0x7001, 0x4E75)
    a.label('mn')
    w(0x7000, 0x4E75)
    code = a.done(); check_cf(code, M_K)
    return code, dict(a.lab)


def texts(org):
    """Texte + Namenstabelle ab org -> (blob, Adressen)."""
    blob = bytearray(); at = {}
    gtab = org; blob += bytes(4 * len(NAMES))
    for k, s in TXT.items():
        at[k] = org + len(blob); blob += s.encode() + b'\0'
    ga = []
    for s in NAMES:
        ga.append(org + len(blob)); blob += s.encode() + b'\0'
    blob[0:4 * len(NAMES)] = struct.pack('>%dI' % len(NAMES), *ga)
    return bytes(blob), at, gtab


def build():
    tabs = [gg.table(n) for n in GROOVES]
    rnd = M_GD
    gc0, gl0 = build_g(0, rnd)
    tc, _ = gg.build_t(0, gl0['HUM'])
    ptrs_at = (M_T + len(tc) + 3) & ~3
    tc, tlab = gg.build_t(ptrs_at, gl0['HUM'])
    t_first = ptrs_at + 4 * GMAX
    place = [t_first, M_T2, M_T2 + 128, M_T3, M_T3 + 128, M_T4, M_T4 + 128]
    tdata = bytes(tc) + bytes(ptrs_at - M_T - len(tc)) + struct.pack('>%dI' % GMAX, *place) + tabs[0][0]
    t2 = tabs[1][0] + tabs[2][0]; t3 = tabs[3][0] + tabs[4][0]; t4 = tabs[5][0] + tabs[6][0]
    gc, gl = build_g(tlab['T'], rnd)
    assert gl['HUM'] == gl0['HUM']
    # M_K: Code, dann Texte; M_GD: RND (8 B) + HUM
    tblob, txt, gnames = texts(M_TX)
    hum, hl = build_hum(M_GD + 8, txt)
    kc, kl = build_k(hl['HUM'], txt, gnames)
    kblob = kc
    data = struct.pack('>I', 0x1234567) + bytes(4) + hum
    parts = {M_G: gc, M_GD: data, M_T: tdata, M_T2: t2, M_T3: t3, M_T4: t4, M_K: kblob, M_TX: tblob}
    lab = dict(G=gl['G'], HUMC=gl['HUM'], T=tlab['T'], HUM=hl['HUM'], GRH=kl['GRH'], MK=kl['MK'], RND=rnd, GNAMES=gnames)
    return parts, lab, place


def hook_bytes(g):
    b = jsr(g) + struct.pack('>H', 0x6000 | (BACK - (HOOK + 8)))
    b += bytes.fromhex("4e71") * ((ORIG[0] - len(b)) // 2)
    assert len(b) == ORIG[0]; return b


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab, place = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(HOOK, ORIG, hook_bytes(lab['G']))
    W.hook(M_HOOK, M_ORIG, jsr(lab['MK']))
    core.slot_write(W, 'groove', lab['GRH'])
    return patch('groove', 9, 'Grooves and humanize',
                 ["FUNC + Swing = groove, Swing per track = amount; SETTINGS / MACHINE + Swing = humanize timing / velocity",
                  "(with TRACK: all tracks, relative or absolute as set by control-mode). Stored per pattern. MACHINE menu opens on release.",
                  "Erzeugt von v2/g2_groove.py."],
                 W, requires=['core'], hooks=[f"{HOOK:#x}", f"{M_HOOK:#x}"],
                 memory=[{"va": f"{MPEND:#x}", "size": 4, "ram": True, "use": "MACHINE pressed (in core VARS)"}],
                 pattern=f"header bytes {C.P_HUM_T}..{C.P_HUM_T + 5} humanize timing, {C.P_HUM_V}..{C.P_HUM_V + 5} humanize velocity, "
                         f"{C.P_GROOVE} groove 0..7",
                 symbols={k: f"{v:#x}" for k, v in lab.items()},
                 params={"slot": C.SLOT['groove'], "gmax": GMAX, "hmax": HMAX, "hk": HK, "names": NAMES,
                         "tabs": [f"{x:#x}" for x in place]})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, _ = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items()})
