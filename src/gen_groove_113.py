#!/usr/bin/env python3
"""Tweak 'groove' fuer die OFFIZIELLE Model:Cycles OS 1.13: Grooves (global) + Humanize (pro Track, pro Pattern gespeichert).
Konzept (Pip, 25.10.2026): Groove als Oberbegriff, Humanize als eigener Wert, der zusaetzlich wirkt.
Setzt die Kette bis 'load-meter' voraus (Encoder-Kette SPG -> SP3 -> SP2 -> SP -> H4, Anzeige aus mod-delays).

Bedienung:
  FUNC + Swing:      Groove waehlen (global, Byte 0x404e9b5e): Swing (Original) -> Hip Hop -> Disco -> Reggaeton.
                     4 Rastungen je Schritt (SLOW), Anzeige "GROOVE <Name>". (NUDGE ist TRIG + Swing, bleibt unberuehrt.)
  Swing (pro Track): Staerke des Grooves auf diesem Track (0..30, wie das Original-Swing; Pattern-Swing gilt wie im Original).
  SETTINGS + Swing:  Humanize ZEIT des ausgewaehlten Tracks im laufenden Pattern (0..100), Popup 'Hum Time / Track'.
  MACHINE + Swing:   Humanize VELOCITY (0..100), Popup 'Hum Vel / Track'. MACHINE oeffnet das Maschinen-Menue dafuer erst
                     beim Loslassen (Haken MK 0x4001ca1e), nicht mehr beim Druecken; nach einer Drehung gar nicht.
  mit TRACK dazu:    CONTROL ALL, alle 6 Tracks relativ, Popup '... / All'.
  Humanize wirkt zusaetzlich auf jeden Groove, auch auf Swing.
Klang (Port aus gen_groove2 v16 / OS-2.0-Linie, gleicher Haken):
  Haken im Ereignisbau 0x400548ce bei 0x40054af8 (Swing-Addition, 20 B) -> jsr G ; bra 0x40054b0c.
  Register dort: d0 Swing (0..30), a0 Faktor der Spurgeschwindigkeit, d1 Trig-Bits (0x10 = Swing-Step), d3 Step,
  d5 Zeitversatz (1500er-Einheiten), d6 Track, a3 Pattern (B), Velocity bei 0x34(a7) in G, Faktor-Byte bei 0x3e(a7).
  Tabellen-Grooves: Versatz = off/256 Step * Swing/30 ; v' = v - v*(127-g)*Swing/6355 (grooves/grooves.json).
  Humanize h (0..100) -> s = (h*77) >> 7 (0..60; v1 >> 8 war Pip zu wenig). Bei 100: Zeit bis +-0.15 Step
    (+-19 ms bei 120 BPM), Velocity bis +-29 % (Zufall: LCG 1664525 / 1013904223).
Speicher Humanize (Zeit 40..45, Velocity 46..51): Pattern-Kopf B+30642 (64 B; Laden 0x4005b3b4 kopiert nur Felder 0..28 und 38, Speichern 0x4005ba0a
  alle 64, Kopieren 0x4005b4c4 alle 64). Bytes 40..45 = Track 1..6 (Modded-Cycles notes/42 §4: von der Firmware nie
  gelesen). Haken: Laden 0x4005b4b0 (move.b $26(a3),$26(a2) -> jsr HL, kopiert zusaetzlich 40..45), Neues Pattern
  0x4006155e (clr.b d0 ; move.b d0,$26(a0) -> jsr HI, loescht zusaetzlich 40..45). Werte > 100 gelten als 0.
Masken (35x35, 280 B): G + Humanize 0x4014b85c | Daten 0x4014d74c | T + Hip Hop 0x401542f8 | Disco 0x401548b4 |
  Reggaeton 0x4015b8f8 ; (47x47, 376 B): SPG + HL + HI 0x40171f30.
Aufruf: gen_groove_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
from gen_chorusfx import check_cf, COPY, HELD
import gen_overlay_113 as ovl
import gen_moddelay_113 as md
import gen_strum_113 as st
import gen_loadmeter_113 as lm
import gen_digidelay_113 as dd

HOOK, BACK = 0x40054AF8, 0x40054B0C
ORIG = (20, 'a65692740c0add9e748715c4a27b649825c1474bc83b88067f8da8748db7fb9d')   # Swing-Addition der Firmware (Laenge + SHA-256)
GMODE = 0x404E9B5E
M_G, M_GD, M_T, M_T2, M_T3, M_K = 0x4014B85C, 0x4014D74C, 0x401542F8, 0x401548B4, 0x4015B8F8, 0x40171F30
M_T4 = 0x4016F8C8                             # 34x34, 272 B: zwei weitere Tabellen
SIZE = {M_G: 280, M_GD: 280, M_T: 280, M_T2: 280, M_T3: 280, M_K: 376, M_T4: 272}
GMAX = 7
NAMES = ovl.GROOVE_NAMES                       # Anzeige im Popup (gen_overlay_113.build_np)
# Groove 1..7 (0 = Swing der Firmware): Tabellen aus grooves/grooves.json.
GROOVES = ['Boom Bap', 'Disco', 'Reggae', 'Bongo', 'Caixixi', 'Highlife', 'Kuduro']
HDR = 0x77B2                                   # Pattern-Kopf in B
HOFF = 40                                      # Humanize Zeit Track t: Kopf + 40 + t
HOFF_V = 6                                     # Humanize Velocity: Kopf + 46 + t (relativ zu HOFF)
KEY_MACH = 5                                   # MACHINE
MPEND = ovl.VARS + 36                          # MACHINE gedrueckt, Menue noch nicht geoeffnet
M_HOOK, M_ORIG, M_MENU = 0x4001CA1E, (6, '3374fc2978b028169697e569b8638f45c7f1da6f4fd2f4c0ff3045433610f566'), 0x4001CA2A
HMAX, HK, HSH = 100, 77, 7                     # s = (h*77) >> 7 (doppelt so stark wie v1, Pip 25.10.2026)
ENC_SW, KEY_FUNC = 12, 1
CUR_PAT = 0x40A7887C                           # *(...) = laufendes Pattern (B)
SEL_A, SEL_B, SEL_C = 0x400CF866, 0x4000EB90, 0x40012412   # ausgewaehlter Track = C(B(A()))
L_HOOK, L_ORIG = 0x4005B4B0, (6, 'ee28f31fe8e35208eaefb6360d0d28dc613f50670d545cf89908a49f66d0d7d2')
I_HOOK, I_ORIG = 0x4006155E, (6, 'f0f7ff9828d5fef4204e8fc3ba19a4718d910f35a87bb54b8cc1d3d83f638d74')
NE, EQ, LE, GE, HI, LS, PL, MI, CS, BRA, BSR, GT = 0x6, 0x7, 0xF, 0xC, 0x2, 0x3, 0xA, 0xB, 0x5, 0x0, 0x1, 0xE


def table(name):
    """Groove-Tabelle aus grooves/grooves.json (Eintrag mit dem Index von name)."""
    d = json.load(open(pathlib.Path(__file__).resolve().parents[1] / 'grooves' / 'grooves.json'))
    i = GROOVES.index(name) + 1
    g = next(x for x in d['grooves'] if x['index'] == i)
    g = dict(g, off=g['offset_256th_step'], vel=g['velocity'])
    return struct.pack('64b', *g['off']) + bytes(g['vel']), g


def build_g2(t_addr, rnd):
    """G mit Humanize; Adressierung des Kopfbytes ueber lea (d16 ist zu gross fuer (d8,An,Xn))."""
    a = A(M_G); w, l = a.w, a.l32
    a.label('G')
    w(0x7E00, 0x1E39); l(GMODE)                 # moveq #0,d7 ; move.b GMODE,d7
    w(0x4A87); a.bcc(NE, 'g1')
    a.orig(HOOK, 6); a.bcc(EQ, 'HUM')           # Original-Swing: verschobene Befehle (aus dem Image)
    a.orig(HOOK + 8, 12)
    a.bcc(BRA, 'HUM')
    a.label('g1')
    w(0x0C87); l(GMAX); a.bcc(HI, 'HUM')        # ungueltig: kein Groove
    w(0x4EF9); l(t_addr)                        # T (springt am Ende nach HUM)
    a.label('HUM')
    w(0x7E05, 0xBE86); a.bcc(CS, 'ret')         # moveq #5,d7 ; cmp.l d6,d7 ; bcs ret   (Track > 5)
    w(0x41EB, HDR + HOFF)                       # lea HDR+HOFF(a3),a0
    w(0x7000, 0x1030, 0x6800)                   # d0 = Humanize Zeit   (Kopf 40+t)
    w(0x7200, 0x1230, 0x6800 | HOFF_V)          # d1 = Humanize Velocity (Kopf 46+t)
    w(0x0C80); l(HMAX); a.bcc(LS, 'a1'); w(0x7000)   # > 100: Muell -> 0
    a.label('a1')
    w(0x0C81); l(HMAX); a.bcc(LS, 'a2'); w(0x7200)
    a.label('a2')
    w(0x7E00 | HK, 0x4C07, 0x0800, 0xEE80)      # st = (ht*77) >> 7  (0..60; v1: >> 8, 0..30)
    w(0x4C07, 0x1800, 0xEE81)                   # sv = (hv*77) >> 7
    w(0x2041)                                   # movea.l d1,a0   sv (Velocity)
    w(0x2E00, 0x8E81); a.bcc(EQ, 'ret')         # beide 0: nichts
    # ab hier wie v16-Humanize: Zeit mit st (d0), Velocity mit sv (a0)
    w(0x732F, 0x003E)                           # mvs.b 0x3e(a7),d1   Faktor
    a.orig(HOOK + 10, 8)                        # d1 = Faktor*12*st = S (Rechnung der Firmware, aus dem Image)
    w(0x2E39); l(rnd)                           # move.l RND,d7
    w(0x203C); l(1664525)
    w(0x4C00, 0x7800)                           # muls.l d0,d7
    w(0x0687); l(1013904223)
    w(0x23C7); l(rnd)                           # move.l d7,RND
    w(0x2007, 0x4840)
    w(0x0280); l(0x7FFF)
    w(0x0480); l(0x4000)
    w(0x4C01, 0x0800)
    w(0xE080, 0xE080, 0xE280)                   # -> +-S/8
    w(0xDA80)                                   # Zeit
    w(0x2007, 0xE288)
    w(0x0280); l(0x7FFF)
    w(0x0480); l(0x4000)
    w(0x2208)                                   # move.l a0,d1   s
    w(0x4C01, 0x0800)                           # r*s
    w(0x222F, 0x0034)                           # Velocity v
    w(0x4A81); a.bcc(LE, 'ret')
    w(0x4C01, 0x0800)                           # r*s*v
    w(0x2E00, 0xE588, 0xD087)                   # *5
    w(0x0680); l(0x800000)
    w(0x7E18, 0xEEA0)                           # asr.l #24
    w(0xD280, 0x7001, 0xB081); a.bcc(LE, 'v1'); w(0x2200)
    a.label('v1')
    w(0x707F, 0xB081); a.bcc(GE, 'v2'); w(0x2200)
    a.label('v2')
    w(0x2F41, 0x0034)
    a.label('ret')
    w(0x4E75)
    code = a.done(); check_cf(code, M_G); assert len(code) <= SIZE[M_G], len(code)
    return code, dict(a.lab)


def build_t(ptrs_at, hum):
    a = A(M_T); w, l = a.w, a.l32
    a.label('T')
    w(0x0C87); l(GMAX); a.bcc(HI, 'out')
    w(0x2F02)                                   # move.l d2,-(a7)  (Velocity jetzt bei 0x38(a7))
    w(0x3208)                                   # move.w a0,d1     Faktor
    w(0x5387, 0xE58F)                           # subq.l #1,d7 ; lsl.l #2,d7   (Modus 1..3)
    w(0x41F9); l(ptrs_at)
    w(0x2070, 0x7800)
    w(0x2E03, 0x0287); l(63)
    w(0x7530, 0x7800)                           # Versatz
    w(0x4C00, 0x2800, 0x4C01, 0x2800)
    w(0x2202, 0xE58A, 0xD481, 0xEC82)
    w(0xDA82)
    w(0x75B0, 0x7840)                           # Groove-Velocity g
    w(0x727F, 0x9282, 0x4C00, 0x1800)
    w(0x242F, 0x0038, 0x4A82); a.bcc(LE, 'done')
    w(0x4C02, 0x1800, 0x2E3C); l(165); w(0x4C07, 0x1800)
    w(0x7E14, 0xEEA1, 0x9481)
    w(0x7201, 0xB282); a.bcc(LE, 'vok'); w(0x2401)
    a.label('vok')
    w(0x2F42, 0x0038)
    a.label('done')
    w(0x241F)
    a.label('out')
    w(0x4EF9); l(hum)                           # weiter mit Humanize
    code = a.done(); check_cf(code, M_T)
    return code, dict(a.lab)


def build_k2(sp_next, names_at, slow, ovs, humg, humv):
    a = A(M_K); w, l = a.w, a.l32
    V = ovl.VARS
    a.label('SPG')
    w(0x202A, 0x0004, 0x0C80); l(ENC_SW); a.bcc(NE, 'nx')
    w(0x712A, 0x0008); a.bcc(EQ, 'nx')
    w(0x4878, md.KEY_SET, 0x4EB9); l(HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'nf')
    w(0x4EF9); l(humg)                          # SETTINGS: Humanize Zeit (Code in der Daten-Maske)
    a.label('nf')
    w(0x4878, KEY_MACH, 0x4EB9); l(HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'nm')
    w(0x4EF9); l(humv)                          # MACHINE: Humanize Velocity
    a.label('nm')
    w(0x4878, KEY_FUNC, 0x4EB9); l(HELD); w(0x588F, 0x4A80); a.bcc(NE, 'grv')
    a.label('nx'); w(0x4EF9); l(sp_next)
    # ---- Groove (FUNC + Swing)
    a.label('grv')
    w(0x4FEF, 0xFFF8, 0x48D7, 0x0030)           # lea -8(a7),a7 ; movem.l d4-d5,(a7)
    w(0x792A, 0x0008, 0x2A3C); l(GMODE)         # mvs.b 8(a2),d4 ; move.l #GMODE,d5 (Ziel fuer SLOW)
    w(0x4EB9); l(slow); w(0x4A80); a.bcc(EQ, 'gsk')   # noch keine volle Stufe
    w(0x7000, 0x1039); l(GMODE)
    w(0x0C80); l(GMAX); a.bcc(LS, 'g0'); w(0x7000)
    a.label('g0')
    w(0x4A84); a.bcc(MI, 'gdn')
    w(0x0C80); l(GMAX); a.bcc(EQ, 'gsh'); w(0x5280); a.bcc(BRA, 'gst')
    a.label('gdn')
    w(0x4A80); a.bcc(EQ, 'gsh'); w(0x5380)
    a.label('gst')
    w(0x13C0); l(md.SCRATCH)
    w(0x4878, 0x0001, 0x4879); l(md.SCRATCH); w(0x4879); l(GMODE)
    w(0x4EB9); l(COPY); w(0x4FEF, 0x000C)
    a.label('gsh')
    w(0x7000, 0x1039); l(GMODE)
    w(0x0C80); l(GMAX); a.bcc(LS, 'g2'); w(0x7000)
    a.label('g2')
    w(0x2200, 0x7004, 0x4EB9); l(ovs)           # OVS(4, Groove)  (Popup zeigt den Namen)
    a.label('gsk')
    w(0x4CD7, 0x0030, 0x4FEF, 0x0008)
    a.bcc(BRA, 'skip')
    a.label('skip')
    w(0x4FEF, 0x000C, 0x4EF9); l(md.ENC_SKIP)
    # ---------------- HL: Pattern laden, zusaetzlich Humanize-Bytes 40..51 (a3 = Datei-Kopf, a2 = B-Kopf, d0 bleibt 1)
    a.label('HL')
    a.orig(L_HOOK, 6)                           # verschobener Originalbefehl
    w(0x41EB, HOFF, 0x43EA, HOFF, 0x720B)
    a.label('hl'); w(0x12D8, 0x5381); a.bcc(PL, 'hl')   # move.b (a0)+,(a1)+ ; subq.l #1,d1 ; bpl
    w(0x4E75)
    # ---------------- HI: neues Pattern (a0 = Kopf), Humanize 0 ; d0.b = 0 wie im Original
    a.label('HI')
    a.orig(I_HOOK, 6)                           # verschobene Originalbefehle
    w(0x43E8, HOFF, 0x720B)
    a.label('hi'); w(0x4219, 0x5381); a.bcc(PL, 'hi')   # clr.b (a1)+
    w(0x4E75)
    # ---------------- MK: MACHINE im Hauptbildschirm (0x4001ca1e, statt move.l d3,-(a7) ; jsr (a3) ; addq.l #4,a7):
    #   Druecken oeffnet das Maschinen-Menue nicht sofort (sonst steht es bei MACHINE + Swing offen), sondern erst beim
    #   Loslassen, wenn dazwischen nicht gedreht wurde (die Geste ruft consume(5), dann kommt kein Loslassen).
    a.label('MK')
    w(0x2043, 0x2028, 0x0010, 0x7209, 0xC081, 0x5380); a.bcc(NE, 'mr')   # erstes Druecken?
    w(0x7001, 0x23C0); l(MPEND); w(0x588F, 0x4EF9); l(ovl.K_DONE)          # merken, Fall erledigt
    a.label('mr')
    w(0x2028, 0x0010, 0x0800, 0x0004); a.bcc(EQ, 'mn')                     # Loslassen?
    w(0x4AB9); l(MPEND); a.bcc(EQ, 'mn')
    w(0x42B9); l(MPEND); w(0x7001, 0x4E75)                                 # d0 = 1: Menue jetzt oeffnen
    a.label('mn')
    w(0x7000, 0x4E75)                                                      # d0 = 0: Standard (0x4001c608)
    code = a.done(); check_cf(code, M_K); assert len(code) <= SIZE[M_K], len(code)
    return code, dict(a.lab)


def build_h(org, ovs):
    """HUMG (SETTINGS + Swing), HL (Laden), HI (neues Pattern) in der Daten-Maske ab org."""
    a = A(org); w, l = a.w, a.l32
    V = ovl.VARS
    a.label('HUMG')                             # Zeit (SETTINGS + Swing)
    w(0x7000); a.bcc(BRA, 'hc')
    a.label('HUMV')                             # Velocity (MACHINE + Swing)
    w(0x7000 | HOFF_V)
    a.label('hc')
    w(0x4FEF, 0xFFEC, 0x48D7, 0x043C)           # lea -20(a7),a7 ; movem.l d2-d5/a2,(a7)
    w(0x2A00)                                   # d5 = 0 (Zeit) / 6 (Velocity)
    w(0x700D, 0x4A85); a.bcc(EQ, 'k1'); w(0x7000 | KEY_MACH)
    a.label('k1')
    w(0x2F00, 0x4EB9); l(md.CONSUME); w(0x588F)   # consume(SETTINGS bzw. MACHINE): kein Menue beim Loslassen
    w(0x42B9); l(V + ovl.PEND); w(0x42B9); l(MPEND)
    w(0x772A, 0x0008)                           # mvs.b 8(a2),d3   Drehung
    w(0x4878, 0x0002, 0x4EB9); l(HELD); w(0x588F, 0x2800)   # d4 = TRACK gehalten (CONTROL ALL: alle Tracks)
    w(0x4EB9); l(SEL_A); w(0x2F00, 0x4EB9); l(SEL_B); w(0x2F00, 0x4EB9); l(SEL_C); w(0x508F)   # d0 = Track
    w(0x7205, 0xB280); a.bcc(CS, 'hx')          # Track > 5 (oder < 0)
    w(0x2400)                                   # d2 = Track
    w(0x2479); l(CUR_PAT)                       # movea.l CUR_PAT,a2
    w(0x220A); a.bcc(EQ, 'hx')                  # kein Pattern
    w(0x45EA, HDR + HOFF, 0xD5C5)               # lea HDR+HOFF(a2),a2 ; adda.l d5,a2
    w(0x7200)                                   # d1 = t = 0
    a.label('lp')
    w(0x4A84); a.bcc(NE, 'do')
    w(0xB282); a.bcc(NE, 'nt')                  # nur der ausgewaehlte Track
    a.label('do')
    w(0x7000, 0x1032, 0x1800)                   # d0 = h[t]
    w(0x0C80); l(HMAX); a.bcc(LS, 'h0'); w(0x7000)
    a.label('h0')
    w(0xD083); a.bcc(PL, 'h1'); w(0x7000)        # += Drehung, >= 0
    a.label('h1')
    w(0x0C80); l(HMAX); a.bcc(LE, 'h2'); w(0x7000 | HMAX)
    a.label('h2')
    w(0x1580, 0x1800)                           # h[t] = d0
    a.label('nt')
    w(0x5281, 0x7006, 0xB081); a.bcc(NE, 'lp')
    w(0x7200, 0x1232, 0x2800)                   # Anzeige: Wert des ausgewaehlten Tracks
    w(0x4A84); a.bcc(EQ, 'hd'); w(0x08C1, 0x0008)   # bset #8,d1 : 'All'
    a.label('hd')
    w(0x7005, 0x4A85); a.bcc(EQ, 'k2'); w(0x7006)
    a.label('k2')
    w(0x4EB9); l(ovs)                           # OVS(5 Zeit / 6 Velocity, h | All)
    a.label('hx')
    w(0x4CD7, 0x043C, 0x4FEF, 0x0014)
    w(0x4FEF, 0x000C, 0x4EF9); l(md.ENC_SKIP)
    code = a.done(); check_cf(code, org)
    return code, dict(a.lab)


def build(img, sp_next):
    tabs_g = [table(n) for n in GROOVES]
    rnd = M_GD
    names_at = M_GD + 8
    data = bytearray(struct.pack('>I', 0x1234567) + bytes(4))
    M = md.build(img)
    hc, hlab = build_h(M_GD + len(data), M['ovs']); data += hc
    gc, glab = build_g2(0, rnd)                 # erst fuer HUM-Adresse
    tc, _ = build_t(0, glab['HUM'])
    ptrs_at = (M_T + len(tc) + 3) & ~3
    tc, tlab = build_t(ptrs_at, glab['HUM'])
    # Ablage: Tabelle 1 hinter T + Zeigern, dann je zwei in M_T2, M_T3, M_T4
    t_first = ptrs_at + 4 * GMAX
    place = [t_first, M_T2, M_T2 + 128, M_T3, M_T3 + 128, M_T4, M_T4 + 128]
    assert len(place) == GMAX == len(tabs_g)
    tdata = bytearray(tc) + bytes(ptrs_at - M_T - len(tc)) + struct.pack('>%dI' % GMAX, *place) + tabs_g[0][0]
    t2 = tabs_g[1][0] + tabs_g[2][0]; t3 = tabs_g[3][0] + tabs_g[4][0]; t4 = tabs_g[5][0] + tabs_g[6][0]
    gc, glab = build_g2(tlab['T'], rnd)
    assert len(tdata) <= SIZE[M_T] and len(data) <= SIZE[M_GD]
    kc, klab = build_k2(sp_next, names_at, M['slow'], M['ovs'], hlab['HUMG'], hlab['HUMV'])
    klab.update(hlab)
    return dict(g=gc, t=bytes(tdata), t2=t2, t3=t3, t4=t4, data=bytes(data), k=kc, glab=glab, tlab=tlab, klab=klab,
                rnd=rnd, names_at=names_at, tabs=tuple(place), info=[g for _, g in tabs_g])


def hook_bytes(g):
    b = bytes.fromhex("4eb9") + struct.pack('>I', g) + struct.pack('>H', 0x6000 | (BACK - (HOOK + 8)))
    b += bytes.fromhex("4e71") * ((ORIG[0] - len(b)) // 2)
    assert len(b) == ORIG[0]; return b


def tweak(img):
    base = img
    for t0 in (md.dn.tweak(img)[0], md.ch.tweak(img)[0], md.ph.tweak(img)[0], dd.tweak(img)[0], md.rz.tweak(img)[0],
               md.tweak(img)[0], st.tweak(img)[0], lm.tweak(img)[0]):
        base = dd.apply(base, t0)
    sp3 = int(lm.tweak(img)[0]['symbols']['SP3'], 16)
    D = build(img, sp3)
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    sw = lambda va, new: {"off": va - BASE, "old": bytes(base[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    assert matches(base, HOOK, ORIG)
    assert matches(base, L_HOOK, L_ORIG) and matches(base, I_HOOK, I_ORIG)
    assert matches(base, M_HOOK, M_ORIG)
    assert base[md.H_HOOK-BASE:md.H_HOOK-BASE+6] == jsr(sp3)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    own = {M_G: D['g'], M_GD: D['data'], M_T: D['t'], M_T2: D['t2'], M_T3: D['t3'], M_T4: D['t4'], M_K: D['k']}
    w = []
    for va, b in own.items():
        assert len(b) <= SIZE[va], (hex(va), len(b))
        w += [sw(va, b), sprites.redirect_write(va)]
    w += [sw(HOOK, hook_bytes(D['glab']['G'])), sw(L_HOOK, jsr(D['klab']['HL'])), sw(I_HOOK, jsr(D['klab']['HI'])),
          sw(md.H_HOOK, jsr(D['klab']['SPG'])), sw(M_HOOK, jsr(D['klab']['MK']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "groove", "order": 73, "name": "Grooves (FUNC + Swing) + Humanize pro Track (SETTINGS + Swing)",
         "description": ["Groove global: Swing, Hip Hop, Disco, Reggaeton; Staerke = Swing des Tracks.",
                         "Humanize 0..100 pro Track, im Pattern gespeichert; wirkt zusaetzlich auf jeden Groove.",
                         "Erzeugt von gen_groove_113.py (Groove-Tabellen: grooves/grooves.json)."],
         "device": "Model:Cycles", "os": "1.13", "section": 3,
         "requires": ["delay-notes", "chorus", "phaser", "digi-delay", "razer", "mod-delays", "strum", "load-meter"],
         "hooks": [f"{HOOK:#x}", f"{L_HOOK:#x}", f"{I_HOOK:#x}", f"{md.H_HOOK:#x}", f"{M_HOOK:#x}"],
         "settings": [f"{GMODE:#x} (Groove 0..3)"], "pattern": "Kopf-Bytes 40..45 = Humanize Zeit Track 1..6, 46..51 = Humanize Velocity Track 1..6",
         "memory": [{"va": f"{va:#x}", "size": SIZE[va]} for va in own],
         "symbols": {"G": f"{D['glab']['G']:#x}", "HUM": f"{D['glab']['HUM']:#x}", "T": f"{D['tlab']['T']:#x}",
                     "SPG": f"{D['klab']['SPG']:#x}", "MK": f"{D['klab']['MK']:#x}", "HUMV": f"{D['klab']['HUMV']:#x}", "HL": f"{D['klab']['HL']:#x}", "HI": f"{D['klab']['HI']:#x}",
                     "RND": f"{D['rnd']:#x}", "NAMES": f"{D['names_at']:#x}", "SP3": f"{sp3:#x}"},
         "params": {"gmax": GMAX, "hmax": HMAX, "hk": HK, "hsh": HSH, "hdr": HDR, "hoff": HOFF, "hoff_v": HOFF_V, "mpend": f"{MPEND:#x}", "names": NAMES,
                    "tabs": [f"{x:#x}" for x in D['tabs']], "grooves": [g['name'] for g in D['info']]},
         "writes": w}
    return t, D


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, D = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print({k: len(D[k]) for k in ('g', 't', 'data', 'k')}, t["symbols"])
