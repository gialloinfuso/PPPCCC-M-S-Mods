#!/usr/bin/env python3
"""Mod-Gruppe 'delay-fx' (v2): Digital Delay, VIBDEL, CHODEL auf dem Delay-Platz. Braucht nur 'core'.

Bedienung: TRACK halten + Delay Time drehen (4 Rastungen je Stufe): Delay -> Digital -> VIBDEL -> CHODEL.
  SETTINGS halten + DELAY SEND drehen: Modulations-Speed 0..127 (Popup 'VIBDEL/CHODEL/Delay' / 'Speed').
Gespeichert im Pattern: Kopf-Byte 53 = Typ (0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL; ungueltig = 0),
  Byte 54 = Speed XOR 64 (neues Pattern: 64).
Klang: Byte fuer Byte wie v1 (Schleifen gen_digidelay_113 / gen_moddelay_113). Geaendert:
  MD (Haken 0x4005699c, jsr Delay des Mixers): DSYNC je Block (Pattern-Bytes -> RAM-Spiegel DMIR/SMIR, Namen), dann
  Original / Digital (DD) / VIBDEL-CHODEL (MS; liest DMIR/SMIR statt der v1-Einstellungsbytes).
  W2 (Haken 0x40056a3c, Schreib-DMA): alle eigenen Typen schreiben in die obere Haelfte der Zeile.
  TC: Delay-Zeit wie die Firmware; mit 'delay-notes' (jsr am DSP-Befehl 0x400581b8) dessen exakte Triolen, sonst
  addi.l #$100 (zur Laufzeit erkannt, keine Abhaengigkeit).
  DFXH (Core-Slot 1): TRACK + Delay Time -> MODESW(Byte 53, Max 3, Rueckruf DSYNC).
  DSPD (Core-Slot 1, gleicher Handler): SETTINGS + DELAY SEND -> Speed.
Speicher: 0x40185f48 (Digital-Schleife), 0x40160e6c (Digital-Setup), 0x4018a788 (Mod-Schleife), 0x401904b4 (Mod-Setup),
  0x4018fc74 (MD, DSYNC, W2, TC), 0x40160864 (Namen), 0x40160b6c (Handler + Texte).
RAM: Digital 0x4233c140 (20 B), Mod 0x4233c320 (56 B), DMIR 0x4233c3fd, SMIR 0x4233c3fe; Zeile 0x4a400000 (obere Haelfte).
Aufruf: g2_delayfx.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_fx4 as fx
import gen_digidelay_113 as dd
import gen_moddelay_113 as md

M_DL, M_DS, M_LOOP, M_SETUP, M_MD, M_H = 0x40185F48, 0x40160E6C, 0x4018A788, 0x401904B4, 0x4018FC74, 0x40160B6C
M_NM = 0x40160864
SIZE = {M_DL: 272, M_DS: 280, M_LOOP: 1024, M_SETUP: 376, M_MD: 376, M_H: 280, M_NM: 280}
D_HOOK, W_HOOK = 0x4005699C, 0x40056A3C
STOCK, WRITE_DMA, DSP = fx.STOCK, fx.WRITE_DMA, 0x400581B8
DSTATE, DMAGIC = dd.DSTATE, fx.DMAGIC
DMIR, SMIR = 0x4233C3FD, 0x4233C3FE
DMAX, B_DIG, B_VIB, B_CHO = 3, 1, 2, 3
SPD_X = 64                                    # gespeichert: Speed XOR 64 (neues Pattern = 64)
NAMES = {1: md.NAMES[0], 2: md.NAMES[3], 3: md.NAMES[2]}   # Digi, VIBDEL, CHODEL
POP = {'delay': b"Delay", 'vib': b"VIBDEL", 'cho': b"CHODEL", 'speed': b"Speed"}


def build_ds(loop_at, tc):
    """Digital-Setup wie fx.build_ds ab 'dd' (ohne Moduspruefung, die macht MD), Zeit ueber TC."""
    a = A(M_DS); w, l = a.w, a.l32
    a.label('DD')
    w(0x4FEF, 0xFFD4, 0x48D7, 0x7CFC)
    w(0x206F, 0x0038)
    w(0x7F68, 0x0002, 0xE087, 0x4A87); a.bcc(PL, 'p1'); w(0x7E00)
    a.label('p1')
    w(0x0C87); l(127); a.bcc(LE, 'p2'); w(0x7E7F)
    a.label('p2')
    w(0x203C); l(258); w(0x4C00, 0x7800)
    w(0x2007, 0x4C07, 0x0800, 0xE080, 0xEE80)
    w(0x4C07, 0x0800, 0xE080, 0xEE80)
    w(0x2207, 0xDE87, 0xDE81, 0x9E80, 0xE287)
    w(0x2A47)
    w(0x7150); a.orig(fx.DTIME, 6); w(0x760A); a.orig(fx.DTIME + 10, 6)   # Zeit wie die Firmware (Befehle aus dem Image)
    a.orig(fx.DTIME + 20, 6); w(0x4EB9); l(tc)
    a.orig(fx.DTIME + 32, 14)
    w(0x0C80); l(0x3FC00); a.bcc(LS, 'p3'); w(0x203C); l(0x3FC00)
    a.label('p3')
    w(0x0C80); l(32); a.bcc(CC, 'p4'); w(0x7020)
    a.label('p4')
    w(0x2840)
    w(0x47F9); l(DSTATE)
    w(0x202B, 0x0008, 0x0C80); l(DMAGIC); a.bcc(EQ, 'ok')
    w(0x203C); l(DMAGIC); w(0x2740, 0x0008)
    w(0x7000, 0x2680, 0x2740, 0x000C, 0x2740, 0x0010)
    w(0x200C, 0x2740, 0x0004)
    a.label('ok')
    w(0x2613, 0x282B, 0x0004, 0x2C2B, 0x000C, 0x2C6B, 0x0010)
    w(0x7A20, 0x226F, 0x0030, 0x206F, 0x0034)
    w(0x45F9); l(fx.LINE); w(0x4EF9); l(loop_at)
    code = a.done(); check_cf(code, M_DS)
    return code, a.lab['DD']


def build_setup(loop_at, tc):
    """Mod-Setup wie v1 (md.build_setup), aber Typ/Speed aus den RAM-Spiegeln, v2-Typnummern, Zeit ueber TC."""
    saved = (md.DMODE, md.SPEED, md.B_CHO, md.B_VIB, md.dn.MD)
    md.DMODE, md.SPEED, md.B_CHO, md.B_VIB, md.dn.MD = DMIR, SMIR, B_CHO, B_VIB, tc
    try:
        return md.build_setup(loop_at)
    finally:
        md.DMODE, md.SPEED, md.B_CHO, md.B_VIB, md.dn.MD = saved


def build_md(img, dd_at, ms_at):
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(C.DESC(26) + 0x2C), rd(C.DESC(26) + 0x34), rd(C.DESC(37) + 0x2C), rd(C.DESC(37) + 0x34),
            rd(C.DESC(38) + 0x2C), rd(C.DESC(38) + 0x34)]
    a = A(M_MD); w, l = a.w, a.l32
    # ---------------- MD: statt jsr Delay im Mixer
    a.label('MD')
    a.bcc(BSR, 'DSYNC')
    w(0x7200, 0x1239); l(DMIR); a.bcc(NE, 'm1')
    w(0x4EF9); l(STOCK)
    a.label('m1')
    w(0x0C81); l(B_DIG); a.bcc(NE, 'm2'); w(0x4EF9); l(dd_at)
    a.label('m2'); w(0x4EF9); l(ms_at)
    # ---------------- DSYNC: Pattern-Bytes -> DMIR/SMIR, Namen (veraendert d0, d1, a0, a1)
    a.label('DSYNC')
    w(0x7200, 0x2039); l(C.CUR_PAT); a.bcc(EQ, 'dz')
    w(0x2040, 0x73A8, C.HDR + C.P_DFX)          # movea.l d0,a0 ; mvz.b HDR+53(a0),d1
    w(0x0C81); l(DMAX); a.bcc(LS, 'd1'); w(0x7200)
    a.label('d1')
    w(0x71A8, C.HDR + C.P_DSPD)                 # mvz.b HDR+54(a0),d0
    w(0x0A80); l(SPD_X); w(0x0C80); l(127); a.bcc(LS, 'd2')
    a.label('dz'); w(0x7000 | SPD_X)
    a.label('d2')
    w(0x13C0); l(SMIR); w(0x13C1); l(DMIR)
    w(0x2001, 0xE788, 0x2200, 0xD080, 0xD081)   # d0 = Typ * 24
    w(0x43F9); l(0); fix_rows = len(a.b) - 4
    w(0xD3C0)
    w(0x41F9); l(C.DESC(26) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41F9); l(C.DESC(37) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41E8, 0x0038, 0x2099, 0x2159, 0x0008)
    w(0x4E75)
    # ---------------- W2: Schreib-DMA; eigene Typen in die obere Haelfte
    a.label('W2')
    w(0x7000, 0x1039); l(DMIR); a.bcc(EQ, 'wgo')
    w(0x2039); l(0x8000B988); w(0x0080); l(0x40000); w(0x23C0); l(0x8000B988)
    a.label('wgo'); w(0x4EF9); l(WRITE_DMA)
    # ---------------- TC: Delay-Zeit (d0) wie am DSP-Befehl der Firmware; d1/a1 bleiben
    a.label('TC')
    w(0x4FEF, 0xFFF8, 0x48D7, 0x0202)           # lea -8(a7),a7 ; movem.l d1/a1,(a7)
    w(0x43F9); l(DSP); w(0x73D1, 0x0C81); l(0x4EB9); a.bcc(NE, 'pl')   # lea DSP,a1 ; mvz.w (a1),d1 ; cmpi.l #jsr,d1
    w(0x2269, 0x0002, 0x2217, 0x4E91); a.bcc(BRA, 'tx')                # movea.l 2(a1),a1 ; move.l (a7),d1 ; jsr (a1)
    a.label('pl'); a.orig(DSP, 6)               # Befehl der Firmware am DSP-Haken (aus dem Image)
    a.label('tx'); w(0x4CD7, 0x0202, 0x4FEF, 0x0008, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_MD)
    rows = M_NM; at = rows + 4 * 24; strs = b''; pool = {}; ptrs = []
    def put(s):
        nonlocal strs
        if s not in pool: pool[s] = at + len(strs); strs += s + b'\0'
        return pool[s]
    for t in range(DMAX + 1):
        ptrs += orig if t == 0 else [put(x) for x in NAMES[t]]
    nm = struct.pack('>24I', *ptrs) + strs
    code[fix_rows:fix_rows + 4] = struct.pack('>I', rows)
    return bytes(code), nm, dict(a.lab, ROWS=rows)


def build_h(dsync):
    cs = core.sym()
    a = A(M_H); w, l = a.w, a.l32
    fix = {}
    def lea(key, reg):                         # lea TEXT,a0 / a1
        w(0x41F9 | (reg << 9)); l(0); fix.setdefault(key, []).append(len(a.b) - 4)
    a.label('DFXH')
    w(0x202A, 0x0004, 0x0C80); l(C.ENC_DTIME); a.bcc(NE, 'sp')
    # TRACK + Delay Time -> Effektwahl
    w(0x4878, C.KEY_TRACK, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'no')
    w(0x2039); l(C.CUR_PAT); a.bcc(EQ, 'no')
    w(0x2040, 0x41E8, C.HDR + C.P_DFX, 0x7200 | DMAX)
    w(0x43F9); l(dsync); w(0x4EF9); l(cs['MODESW'])
    # SETTINGS + DELAY SEND -> Speed
    a.label('sp')
    w(0x0C80); l(C.ENC_DSEND); a.bcc(NE, 'no')
    w(0x712A, 0x0008); a.bcc(EQ, 'no')
    w(0x4878, C.KEY_SET, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'no')
    w(0x7000 | C.KEY_SET, 0x4EB9); l(cs['GEST'])
    w(0x2039); l(C.CUR_PAT); a.bcc(EQ, 'sk')
    w(0x2040, 0x41E8, C.HDR + C.P_DSPD)         # a0 = &Speed-Byte
    w(0x7190, 0x0A80); l(SPD_X); w(0x0C80); l(127); a.bcc(LS, 's0'); w(0x7000 | SPD_X)
    a.label('s0')
    w(0x732A, 0x0008, 0xD081); a.bcc(PL, 's1'); w(0x7000)
    a.label('s1')
    w(0x0C80); l(127); a.bcc(LE, 's2'); w(0x707F)
    a.label('s2')
    w(0x2200, 0x0A80); l(SPD_X); w(0x1080)      # d1 = Speed ; Byte = Speed ^ 64
    w(0x71A8, 0xFFFF)                           # mvz.b -1(a0),d0   Typ
    lea('delay', 1)
    w(0x0C80); l(B_VIB); a.bcc(NE, 't3'); lea('vib', 1); a.bcc(BRA, 't4')
    a.label('t3')
    w(0x0C80); l(B_CHO); a.bcc(NE, 't4'); lea('cho', 1)
    a.label('t4')
    w(0x2049); lea('speed', 1)                  # movea.l a1,a0 ; lea 'Speed',a1
    w(0x7000 | C.OV_NUM, 0x4EB9); l(cs['OVS'])
    a.label('sk'); w(0x7001, 0x4E75)
    a.label('no'); w(0x7000, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_H)
    at = {}
    for k, s in POP.items():
        at[k] = M_H + len(code); code += s + b'\0'
    for k, offs in fix.items():
        for o in offs: code[o:o + 4] = struct.pack('>I', at[k])
    return bytes(code), dict(a.lab)


def build(img):
    dl = dd.build_dl()
    loop = md.build_loop()
    # TC liegt in M_MD: Adresse aus einem ersten Durchlauf
    _, _, lab0 = build_md(img, 0, 0)
    tc = lab0['TC']
    ds, dd_at = build_ds(M_DL, tc)
    setup, ms_at = build_setup(M_LOOP, tc)
    mdc, nm, lab = build_md(img, dd_at, ms_at)
    assert lab['TC'] == tc
    hc, hl = build_h(lab['DSYNC'])
    lab.update(hl); lab.update(DD=dd_at, MS=ms_at)
    parts = {M_DL: dl, M_DS: ds, M_LOOP: loop, M_SETUP: setup, M_MD: mdc, M_H: hc, M_NM: nm}
    return parts, lab


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build(img)
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(D_HOOK, jsr(STOCK), jsr(lab['MD']))
    W.hook(W_HOOK, jsr(WRITE_DMA), jsr(lab['W2']))
    core.slot_write(W, 'delay-fx', lab['DFXH'])
    return patch('delay-fx', 6, 'Delay FX: Digital delay, VIBDEL, CHODEL',
                 ["TRACK + Delay Time: Delay -> Digital -> VIBDEL -> CHODEL; SETTINGS + DELAY SEND = modulation speed.",
                  "Stored per pattern (header bytes 53, 54). Erzeugt von v2/g2_delayfx.py."], W, requires=['core'],
                 hooks=[f"{D_HOOK:#x}", f"{W_HOOK:#x}"],
                 memory=[{"va": f"{DSTATE:#x}", "size": 20, "ram": True, "use": "digital delay state"},
                         {"va": f"{md.MSTATE:#x}", "size": 56, "ram": True, "use": "VIBDEL/CHODEL state"},
                         {"va": f"{DMIR:#x}", "size": 2, "ram": True, "use": "type + speed mirror"}],
                 pattern=f"header byte {C.P_DFX}: 0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL; byte {C.P_DSPD}: speed XOR 64",
                 symbols={k: f"{v:#x}" for k, v in lab.items() if k.isupper()},
                 params={"slot": C.SLOT['delay-fx'], "dmir": f"{DMIR:#x}", "smir": f"{SMIR:#x}", "spd_xor": SPD_X})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build(stock())
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
