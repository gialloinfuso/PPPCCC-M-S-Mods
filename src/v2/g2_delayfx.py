#!/usr/bin/env python3
"""Mod-Gruppe 'delay-fx' (v2): Digital Delay, VIBDEL, CHODEL auf dem Delay-Platz. Braucht nur 'core'.

Bedienung: TRACK halten + Delay Time drehen (4 Rastungen je Stufe): Delay -> Digital -> VIBDEL -> CHODEL.
  FUNC halten + DELAY SEND drehen (smp39; vorher SETTINGS): Modulations-Speed 0..127 (Popup 'VIBDEL/CHODEL/Delay' / 'Speed').
Gespeichert im Pattern: Kopf-Byte 53 = Typ (0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL; ungueltig = 0),
  Byte 54 = Speed XOR 64 (neues Pattern: 64).
Klang: Byte fuer Byte wie v1 (Schleifen gen_digidelay_113 / gen_moddelay_113). Geaendert:
  MD (Haken 0x4005699c, jsr Delay des Mixers): DSYNC je Block (Pattern-Bytes -> RAM-Spiegel DMIR/SMIR, Namen), dann
  Original / Digital (DD) / VIBDEL-CHODEL (MS; liest DMIR/SMIR statt der v1-Einstellungsbytes).
  W2 (Haken 0x40056a3c, Schreib-DMA): alle eigenen Typen schreiben in die obere Haelfte der Zeile.
  TC: Delay-Zeit wie die Firmware; mit 'delay-notes' (jsr am DSP-Befehl 0x400581b8) dessen exakte Triolen, sonst
  addi.l #$100 (zur Laufzeit erkannt, keine Abhaengigkeit).
  DFXH (Core-Slot 1): TRACK + Delay Time -> MODESW(Byte 53, Max 3, Rueckruf DSYNC).
  DSPD (Core-Slot 1, gleicher Handler): FUNC + DELAY SEND -> Speed.
Speicher: 0x40185f48 (Digital-Schleife), 0x40160e6c (Digital-Setup), 0x4018a788 (Mod-Schleife), 0x401904b4 (Mod-Setup),
  0x4018fc74 (MD, DSYNC, W2, TC), 0x40160864 (Namen), 0x40160b6c (Handler + Texte).
RAM: Digital 0x4233c140 (20 B), Mod 0x4233c320 (56 B), DMIR 0x4233c3fd, SMIR 0x4233c3fe; Zeile 0x4a400000 (obere Haelfte).
smp46 (Last): VIBDEL/CHODEL (smp47: auch Digital) lesen die Zeile ueber den gecachten Alias LINE_C (0x42400000, gleicher Speicher), Schreiben
  weiter ungecacht (Speicher immer aktuell, DMA/Umschalten wie vorher). Gleiche Werte: jeder Lesekopf liegt >= 32 Frames
  hinter dem Schreibkopf, eine Cache-Zeile (2 Frames) enthaelt nur fertige Frames; veralten koennte sie erst nach einem
  ganzen Umlauf des Rings (>= 8192 Frames bei schnellstem Gleiten), so lange bleibt keine Zeile im Cache (8 KB).
  Vorher 6 (CHODEL) / 3 (VIBDEL, Digital) ungecachte Zugriffe je Frame, jetzt 1 (Digital 2: L und R).
Aufruf: g2_delayfx.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_fx4 as fx
import gen_digidelay_113 as dd
import gen_moddelay_113 as md
from cfasm import asm, done as adone

M_DL, M_DS, M_LOOP, M_SETUP, M_MD, M_H = 0x40185F48, 0x40160E6C, 0x4018A788, 0x401904B4, 0x4018FC74, 0x40160B6C
M_NM = 0x40160864
SIZE = {M_DL: 272, M_DS: 280, M_LOOP: 1024, M_SETUP: 376, M_MD: 376, M_H: 280, M_NM: 280}
D_HOOK, W_HOOK = 0x4005699C, 0x40056A3C
STOCK, WRITE_DMA, DSP = fx.STOCK, fx.WRITE_DMA, 0x400581B8
DSTATE, DMAGIC = dd.DSTATE, fx.DMAGIC
DMIR, SMIR = 0x4233C3FD, 0x4233C3FE
DMAX, B_DIG, B_VIB, B_CHO = 3, 1, 2, 3
LINE_C = fx.LINE - 0x08000000                 # smp46: gecachter Alias der Zeile (0x42400000)
SPD_X = 64                                    # gespeichert: Speed XOR 64 (neues Pattern = 64)
# smp22 (Pip 04.11.): Anzeige 'ViDel' / 'ChDel' statt VIBDEL / CHODEL (kurz 'ViDl' / 'ChDl')
NAMES = {1: md.NAMES[0],
         2: (b"ViDel Send", b"ViDl", b"ViDel Time", b"TIME", b"ViDel Fdbk", b"FDBK"),
         3: (b"ChDel Send", b"ChDl", b"ChDel Time", b"TIME", b"ChDel Fdbk", b"FDBK")}
POP = {'delay': b"Delay", 'vib': b"ViDel", 'cho': b"ChDel", 'speed': b"Speed"}


def build_ds(loop_at, tc):
    """Digital-Setup wie fx.build_ds ab 'dd' (ohne Moduspruefung, die macht MD), Zeit ueber TC."""
    a = A(M_DS)
    asm(a, f'''
    DD:     lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 56(sp),a0                ; params
            mvs.w   2(a0),d7
            asr.l   #8,d7                    ; Feedback 0..127
            tst.l   d7
            bpl     p1
            moveq   #0,d7
    p1:     cmpi.l  #127,d7
            ble     p2
            moveq   #127,d7
    p2:     move.l  #258,d0
            muls.l  d0,d7
            move.l  d7,d0
            muls.l  d7,d0
            asr.l   #8,d0
            asr.l   #7,d0
            muls.l  d7,d0
            asr.l   #8,d0
            asr.l   #7,d0
            move.l  d7,d1
            add.l   d7,d7
            add.l   d1,d7
            sub.l   d0,d7
            asr.l   #1,d7                    ; (3f - f^3)/2
            movea.l d7,a5                    ; Rueckkopplung
    ; Zeit wie die Firmware (Befehle aus dem Image)
            mvs.w   (a0),d0
            orig    {fx.DTIME:#x},6
            moveq   #10,d3
            orig    {fx.DTIME + 10:#x},6
            orig    {fx.DTIME + 20:#x},6
            jsr     {tc:#x}
            orig    {fx.DTIME + 32:#x},14
            cmpi.l  #0x3fc00,d0
            bls     p3
            move.l  #0x3fc00,d0
    p3:     cmpi.l  #32,d0
            bcc     p4
            moveq   #32,d0
    p4:     movea.l d0,a4                    ; Verzoegerung in Samples
            lea     {DSTATE:#x},a3
            move.l  8(a3),d0
            cmpi.l  #{DMAGIC:#x},d0
            beq     ok
            move.l  #{DMAGIC:#x},d0          ; Zustand erstmals leeren
            move.l  d0,8(a3)
            moveq   #0,d0
            move.l  d0,(a3)
            move.l  d0,12(a3)
            move.l  d0,16(a3)
            move.l  a4,d0
            move.l  d0,4(a3)
    ok:     move.l  (a3),d3
            move.l  4(a3),d4
            move.l  12(a3),d6
            movea.l 16(a3),a6
            moveq   #32,d5
            movea.l 48(sp),a1                ; out
            movea.l 52(sp),a0                ; in
            lea     {LINE_C:#x},a2               ; smp47: Lesen gecacht (Schreiben: Schleife, ungecacht)
            jmp     {loop_at:#x}
    ''')
    code = adone(a); check_cf(code, M_DS)
    return code, a.lab['DD']


def build_setup(loop_at, tc):
    """Mod-Setup wie v1 (md.build_setup), aber Typ/Speed aus den RAM-Spiegeln, v2-Typnummern, Zeit ueber TC."""
    saved = (md.DMODE, md.SPEED, md.B_CHO, md.B_VIB, md.dn.MD, md.LINE)
    md.DMODE, md.SPEED, md.B_CHO, md.B_VIB, md.dn.MD, md.LINE = DMIR, SMIR, B_CHO, B_VIB, tc, LINE_C   # smp46: a2 gecacht
    try:
        return md.build_setup(loop_at)
    finally:
        md.DMODE, md.SPEED, md.B_CHO, md.B_VIB, md.dn.MD, md.LINE = saved


def build_md(img, dd_at, ms_at):
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(C.DESC(26) + 0x2C), rd(C.DESC(26) + 0x34), rd(C.DESC(37) + 0x2C), rd(C.DESC(37) + 0x34),
            rd(C.DESC(38) + 0x2C), rd(C.DESC(38) + 0x34)]
    rows = M_NM
    a = A(M_MD)
    asm(a, f'''
    ; ---------------- MD: statt jsr Delay im Mixer
    MD:     bsr     DSYNC
            moveq   #0,d1
            move.b  {DMIR:#x},d1
            bne     m1
            jmp     {STOCK:#x}               ; 0: Delay der Firmware
    m1:     cmpi.l  #{B_DIG},d1
            bne     m2
            jmp     {dd_at:#x}               ; Digital
    m2:     jmp     {ms_at:#x}               ; VIBDEL / CHODEL
    ; ---------------- DSYNC: Pattern-Bytes -> DMIR/SMIR, Namen (veraendert d0, d1, a0, a1)
    DSYNC:  moveq   #0,d1
            move.l  {C.CUR_PAT:#x},d0
            beq     dz
            movea.l d0,a0
            mvz.b   {C.HDR + C.P_DFX}(a0),d1 ; Typ
            cmpi.l  #{DMAX},d1
            bls     d1
            moveq   #0,d1
    d1:     mvz.b   {C.HDR + C.P_DSPD}(a0),d0   ; Speed ^ 64
            eori.l  #{SPD_X},d0
            cmpi.l  #127,d0
            bls     d2
    dz:     moveq   #{SPD_X},d0
    d2:     move.b  d0,{SMIR:#x}
            move.b  d1,{DMIR:#x}
            move.l  d1,d0
            lsl.l   #3,d0
            move.l  d0,d1
            add.l   d0,d0
            add.l   d1,d0                    ; d0 = Typ * 24
            lea     {rows:#x},a1
            adda.l  d0,a1
            lea     {C.DTD(26) + 0x2C:#x},a0 ; smp18: Kopie der Deskriptor-Tabelle (Core)
            move.l  (a1)+,(a0)
            move.l  (a1)+,8(a0)
            lea     {C.DTD(37) + 0x2C:#x},a0
            move.l  (a1)+,(a0)
            move.l  (a1)+,8(a0)
            lea     56(a0),a0
            move.l  (a1)+,(a0)
            move.l  (a1)+,8(a0)
            rts
    ; ---------------- W2: Schreib-DMA; eigene Typen in die obere Haelfte
    W2:     moveq   #0,d0
            move.b  {DMIR:#x},d0
            beq     wgo
            move.l  0x8000b988,d0
            ori.l   #0x40000,d0
            move.l  d0,0x8000b988
    wgo:    jmp     {WRITE_DMA:#x}
    ; ---------------- TC: Delay-Zeit (d0) wie am DSP-Befehl der Firmware; d1/a1 bleiben
    TC:     lea     -8(sp),sp
            movem.l d1/a1,(sp)
            lea     {DSP:#x},a1
            mvz.w   (a1),d1
            cmpi.l  #0x4eb9,d1               ; dort ein jsr (delay-notes)?
            bne     pl
            movea.l 2(a1),a1
            move.l  (sp),d1
            jsr     (a1)                     ; dann dessen Funktion
            bra     tx
    pl:     orig    {DSP:#x},6               ; sonst der Befehl der Firmware (aus dem Image)
    tx:     movem.l (sp),d1/a1
            lea     8(sp),sp
            rts
    ''')
    code = adone(a); check_cf(code, M_MD)
    at = rows + 4 * 24; strs = b''; pool = {}; ptrs = []
    def put(s):
        nonlocal strs
        if s not in pool: pool[s] = at + len(strs); strs += s + b'\0'
        return pool[s]
    for t in range(DMAX + 1):
        ptrs += orig if t == 0 else [put(x) for x in NAMES[t]]
    nm = struct.pack('>24I', *ptrs) + strs
    return code, nm, dict(a.lab, ROWS=rows)


def build_h(dsync):
    cs = core.sym()
    text = f'''
    DFXH:   move.l  4(a2),d0
            cmpi.l  #{C.ENC_DTIME},d0
            bne     sp
    ; TRACK + Delay Time -> Effektwahl
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     no
            move.l  {C.CUR_PAT:#x},d0
            beq     no
            movea.l d0,a0
            lea     {C.HDR + C.P_DFX}(a0),a0
            moveq   #{DMAX},d1
            lea     {dsync:#x},a1
            jmp     {cs['MODESW']:#x}
    ; FUNC + DELAY SEND -> Speed (smp39, Pip 11.11.; vorher SETTINGS + DELAY SEND)
    sp:     cmpi.l  #{C.ENC_DSEND},d0
            bne     no
            mvs.b   8(a2),d0                 ; Drehung
            beq     no
            pea     {C.KEY_FUNC}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     no
            moveq   #{C.KEY_FUNC},d0
            jsr     {cs['GEST']:#x}
            move.l  {C.CUR_PAT:#x},d0
            beq     sk
            movea.l d0,a0
            lea     {C.HDR + C.P_DSPD}(a0),a0   ; a0 = &Speed-Byte
            mvz.b   (a0),d0
            eori.l  #{SPD_X},d0
            cmpi.l  #127,d0
            bls     s0
            moveq   #{SPD_X},d0
    s0:     mvs.b   8(a2),d1
            add.l   d1,d0
            bpl     s1
            moveq   #0,d0
    s1:     cmpi.l  #127,d0
            ble     s2
            moveq   #127,d0
    s2:     move.l  d0,d1                    ; d1 = Speed
            eori.l  #{SPD_X},d0
            move.b  d0,(a0)                  ; Byte = Speed ^ 64
            mvz.b   -1(a0),d0                ; Typ
            lea     T_DELAY,a1
            cmpi.l  #{B_VIB},d0
            bne     t3
            lea     T_VIB,a1
            bra     t4
    t3:     cmpi.l  #{B_CHO},d0
            bne     t4
            lea     T_CHO,a1
    t4:     movea.l a1,a0
            lea     T_SPEED,a1               ; Popup: Typ / 'Speed' = Wert
            moveq   #{C.OV_NUM},d0
            jsr     {cs['OVS']:#x}
    sk:     moveq   #1,d0
            rts
    no:     moveq   #0,d0
            rts
'''
    def tail(end):
        b = bytearray(); at = {}
        for k, s in POP.items():
            at['T_' + k.upper()] = end + len(b); b += s + b'\0'
        return bytes(b), at
    code, lab = asm2(M_H, text, tail)
    return code, {k: v for k, v in lab.items() if not k.startswith('T_')}


def build(img):
    dl = dd.build_dl(wr_alias=fx.LINE - LINE_C)          # smp47: Digital wie VIBDEL/CHODEL
    loop = md.build_loop(wr_alias=fx.LINE - LINE_C)     # smp46: Lesen gecacht, Schreiben ungecacht
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
                 ["TRACK + Delay Time: Delay -> Digital -> VIBDEL -> CHODEL; FUNC + DELAY SEND = modulation speed.",
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
