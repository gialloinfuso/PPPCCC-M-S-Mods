#!/usr/bin/env python3
"""Mod-Gruppe 'reverb-fx' (v2): Chorus I / II, Phaser, RAZR auf dem Reverb-Platz. Braucht nur 'core'.

Bedienung: TRACK halten + Reverb Size drehen (4 Rastungen je Stufe, Core MODESW): Reverb -> Chorus I -> Chorus II ->
  Phaser -> RAZR. Die Firmware zeigt danach ihr Parameter-Popup mit den neuen Namen (Ereignis mit Drehung 0).
Gespeichert im Pattern: Kopf-Byte 52 (0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR; ungueltig = 0).
Klang: Byte fuer Byte wie v1 (gen_chorus3 / gen_fx4 / gen_razer_113), gleiche Masken. Geaendert ist nur die Weiche:
  R (Haken 0x40056a2c, jsr Reverb des Mixers) liest das Pattern-Byte je Block (RSYNC), legt es in den RAM-Spiegel RMODE
  (den der Chorus-Setup statt des v1-Einstellungsbytes liest), setzt die Parameternamen (N) und springt zum Effekt.
  RFXH (Core-Slot 0): TRACK + Reverb Size -> MODESW(Pattern-Byte 52, Max 4, Rueckruf RSYNC).
Speicher: Chorus 0x40171bc8 / 0x4016ea78 / 0x401728f8, Phaser 0x4018ff64 / 0x40185648 / 0x401857f8 / 0x4016f7d0,
  RAZR 0x4016cae8, Namen-Texte 0x40179140, Namen-Tabelle + F0 0x4015f50c, Weiche 0x4018af88.
RAM: Chorus 0x4a33a000 (8240 B), Phaser 0x4233c100, RAZR 0x4233c180 / c200 / c210, RMODE 0x4233c3fc.
Aufruf: g2_reverbfx.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_chorus_113 as ch
import gen_chorus3 as c3
import gen_chorusfx as cf
import gen_phaser_113 as ph
import gen_razer_113 as rz

M_SETUP, M_LOOP, M_TAP = ch.M_SETUP, ch.M_LOOP, ch.M_TAP
M_STR, M_TAB, M_UI = 0x40179140, 0x4015F50C, 0x4018AF88
SIZE = {M_SETUP: 184, M_LOOP: 208, M_TAP: 184, M_STR: 184, M_TAB: 280, M_UI: 272,
        ph.M_PP: 272, ph.M_PT: 184, ph.M_PSA: 184, ph.M_PSB: 124, rz.M_RZ: 1024}
R_HOOK, REVERB = 0x40056A2C, 0x400579C4
STATE, CMAGIC = ch.STATE, 0x43484F42        # Chorus-Zustand + Ring (8240 B), 'CHOB' wie v1
RMODE = 0x4233C3FC                          # RAM-Spiegel des Pattern-Bytes (gecacht, nur CPU)
RMAX = 4
ROWS = {1: (b"Cho1 Send", b"CHO1", b"Cho1 Speed", b"SPD", b"Cho1 Depth", b"DEP"),
        2: (b"Cho2 Send", b"CHO2", b"Cho2 Speed", b"SPD", b"Cho2 Depth", b"DEP"),
        3: ph.ROW, 4: rz.ROW}


def build_dsp():
    ch.configure()
    c3.MODE = RMODE                         # v2: Modus aus dem RAM-Spiegel statt aus dem Einstellungsblock
    setup, loop, tap = c3.build()
    tap = tap + bytes(c3.M_TAB - c3.M_TAP - len(tap)) + c3.table()
    P = ph.build_phaser()
    Z = rz.build_razer()
    return dict(setup=setup, loop=loop, tap=tap, P=P, Z=Z)


def build_tables(img):
    """Texte (M_STR) und Tabelle (M_TAB): 5 Zeilen zu 8 Zeigern [Name27, Kurz27, Name39, Kurz39, Name40, Kurz40, Fn39, Fn40],
    Zeile 0 = Original aus dem Image; dahinter F0 (Anzeige 0..127)."""
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(C.DESC(27) + 0x2C), rd(C.DESC(27) + 0x34), rd(C.DESC(39) + 0x2C), rd(C.DESC(39) + 0x34),
            rd(C.DESC(40) + 0x2C), rd(C.DESC(40) + 0x34)]
    strs = b''; pool = {}
    def put(s):
        nonlocal strs
        if s not in pool: pool[s] = M_STR + len(strs); strs += s + b'\0'
        return pool[s]
    f0_at = M_TAB + 32 * (RMAX + 1)
    tab = struct.pack('>8I', *orig, cf.F39_ORIG, cf.F40_ORIG)
    for m in range(1, RMAX + 1):
        tab += struct.pack('>8I', *[put(x) for x in ROWS[m]], f0_at, f0_at)
    tab += cf.F0_code(f0_at)
    return strs, tab


def build_ui(dsp):
    a = A(M_UI); w, l = a.w, a.l32
    # ---------------- R: statt jsr Reverb im Mixer (Stack: ret, out, in, params)
    a.label('R')
    a.bcc(BSR, 'RSYNC')
    w(0x7200, 0x1239); l(RMODE)                 # moveq #0,d1 ; move.b RMODE,d1
    a.bcc(NE, 'rc')
    w(0x4EF9); l(REVERB)
    a.label('rc')
    w(0x0C81); l(3); a.bcc(NE, 'r4'); w(0x4EF9); l(dsp['P']['ph'])
    a.label('r4')
    w(0x0C81); l(4); a.bcc(NE, 'rch'); w(0x4EF9); l(dsp['Z']['rz'])
    a.label('rch')                              # Chorus I / II: Ring beim ersten Mal leeren (Magic)
    w(0x41F9); l(STATE + 8); w(0x2010, 0x0C80); l(CMAGIC); a.bcc(EQ, 'go')
    w(0x41F9); l(STATE); w(0x203C); l(2060)
    a.label('cl'); w(0x4298, 0x5380); a.bcc(NE, 'cl')
    w(0x203C); l(CMAGIC); w(0x41F9); l(STATE + 8); w(0x2080)
    a.label('go'); w(0x4EF9); l(M_SETUP)
    # ---------------- RSYNC: Pattern-Byte -> RMODE, dann Namen (veraendert d0, d1, a0, a1)
    a.label('RSYNC')
    w(0x7200, 0x2039); l(C.CUR_PAT); a.bcc(EQ, 's0')        # moveq #0,d1 ; move.l CUR_PAT,d0 ; beq
    w(0x2040, 0x73A8, C.HDR + C.P_RFX)                       # movea.l d0,a0 ; mvz.b HDR+52(a0),d1
    w(0x0C81); l(RMAX); a.bcc(LS, 's0'); w(0x7200)
    a.label('s0')
    w(0x13C1); l(RMODE)
    # N: Namen + Anzeigefunktionen nach d1
    w(0x2001, 0xEB88, 0x43F9); l(M_TAB); w(0xD3C0)          # move.l d1,d0 ; lsl.l #5,d0 ; lea TAB,a1 ; adda.l d0,a1
    w(0x41F9); l(C.DESC(27) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41F9); l(C.DESC(39) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41E8, 0x0038, 0x2099, 0x2159, 0x0008)
    w(0x23D9); l(cf.FN39); w(0x23D9); l(cf.FN40)
    w(0x4E75)
    code = a.done(); check_cf(code, M_UI)
    return code, dict(a.lab)


def build_rfxh(org, rsync):
    a = A(org); w, l = a.w, a.l32
    # ---------------- RFXH (Core-Slot): TRACK + Reverb Size -> Effektwahl
    a.label('RFXH')
    w(0x202A, 0x0004, 0x0C80); l(C.ENC_RSIZE); a.bcc(NE, 'no')
    w(0x4878, C.KEY_TRACK, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'no')
    w(0x2039); l(C.CUR_PAT); a.bcc(EQ, 'no')
    w(0x2040, 0x41E8, C.HDR + C.P_RFX)          # movea.l d0,a0 ; lea HDR+52(a0),a0
    w(0x7200 | RMAX)                            # moveq #RMAX,d1
    w(0x43F9); l(rsync)                         # lea RSYNC,a1
    w(0x4EF9); l(core.sym()['MODESW'])          # jmp MODESW (liefert d0 = 2)
    a.label('no'); w(0x7000, 0x4E75)
    code = a.done(); check_cf(code, org)
    return code, dict(a.lab)


def build(img):
    D = build_dsp()
    strs, tab = build_tables(img)
    ui, lab = build_ui(D)
    org = (M_TAB + len(tab) + 1) & ~1
    rc, rl = build_rfxh(org, lab['RSYNC'])
    tab = tab + bytes(org - M_TAB - len(tab)) + rc; lab.update(rl)
    P, Z = D['P'], D['Z']
    parts = {M_SETUP: D['setup'], M_LOOP: D['loop'], M_TAP: D['tap'], M_STR: strs, M_TAB: tab, M_UI: ui,
             ph.M_PP: P['pp'], ph.M_PT: P['pt'], ph.M_PSA: P['psa'], ph.M_PSB: P['psb'], rz.M_RZ: Z['blob']}
    lab.update(phaser=P['ph'], razer=Z['rz'], setup=M_SETUP, f0=M_TAB + 32 * (RMAX + 1), tab=M_TAB)
    return parts, lab


def tweak(img):
    """img = Stock-Image; 'old' gegen Stock + Core."""
    base = apply(img, core.tweak(img))
    parts, lab = build(img)
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(R_HOOK, jsr(REVERB), jsr(lab['R']))
    core.slot_write(W, 'reverb-fx', lab['RFXH'])
    return patch('reverb-fx', 5, 'Reverb FX: Chorus I / II, Phaser, RAZR',
                 ["TRACK + Reverb Size: Reverb -> Chorus I -> Chorus II -> Phaser -> RAZR. Stored per pattern (header byte 52).",
                  "Erzeugt von v2/g2_reverbfx.py."], W, requires=['core'],
                 hooks=[f"{R_HOOK:#x}"],
                 memory=[{"va": f"{STATE:#x}", "size": 0x2030, "ram": True, "use": "chorus state + ring"},
                         {"va": f"{ph.PSTATE:#x}", "size": 0x38, "ram": True, "use": "phaser state"},
                         {"va": f"{rz.PSTATE2:#x}", "size": 0x38, "ram": True, "use": "RAZR phaser state"},
                         {"va": f"{rz.RZP:#x}", "size": 4, "ram": True, "use": "RAZR reverb parameters"},
                         {"va": f"{rz.TMP:#x}", "size": 256, "ram": True, "use": "RAZR buffer"},
                         {"va": f"{RMODE:#x}", "size": 1, "ram": True, "use": "mode mirror"}],
                 pattern=f"header byte {C.P_RFX}: 0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR",
                 symbols={k: f"{v:#x}" for k, v in lab.items()},
                 params={"slot": C.SLOT['reverb-fx'], "rmode": f"{RMODE:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build(stock())
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items()})
