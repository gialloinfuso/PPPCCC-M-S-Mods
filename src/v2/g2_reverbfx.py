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
import gen_fx4 as fx
from gen_chorusfx import check_cf
import g2_reverbs as RV
from cfasm import asm, done as adone

M_SETUP, M_LOOP, M_TAP = ch.M_SETUP, ch.M_LOOP, ch.M_TAP
M_STR, M_TAB, M_UI = 0x40179140, 0x4015F50C, 0x4018AF88
SIZE = {M_SETUP: 184, M_LOOP: 208, M_TAP: 184, M_STR: 184, M_TAB: 280, M_UI: 272,
        ph.M_PP: 272, ph.M_PT: 184, ph.M_PSA: 184, ph.M_PSB: 124, rz.M_RZ: 1024}
R_HOOK, REVERB = 0x40056A2C, 0x400579C4
STATE, CMAGIC = ch.STATE, 0x43484F42        # Chorus-Zustand + Ring (8240 B), 'CHOB' wie v1
RMODE = 0x4233C3FC                          # RAM-Spiegel des Pattern-Bytes (gecacht, nur CPU)
RMAX = 7                                    # smp9: + Hall, Room, Plate (Nutzlast, g2_reverbs.py)
ROWS = {1: (b"Cho1 Send", b"CHO1", b"Cho1 Speed", b"SPD", b"Cho1 Depth", b"DEP"),
        2: (b"Cho2 Send", b"CHO2", b"Cho2 Speed", b"SPD", b"Cho2 Depth", b"DEP"),
        3: ph.ROW, 4: (b"Razr Mix", b"Razr", b"Razr Length", b"LEN", b"Razr Speed", b"SPD"),   # smp22: 'Razr' (Pip)
        **RV.ROWS}


RZ_TOUT = rz.TMP + 0x80                     # smp22: Ausgang des Phasers (16 Frames) hinter dem Eingang (16 Frames)


def build_rz2(pass_at, coef_at):
    """smp22 (Pip: weniger CPU): RAZR wie rz.build_rz, der Phaser rechnet aber mit halber Rate. Das Signal ist dort durch
    das Sample-and-Hold x2 schon halbe Rate: jeder zweite Frame -> TMP (16 Frames), Durchlauf wie der Phaser-Modus
    (gleiche Schleife) mit Koeffizienten fuer 24 kHz (Tabelle mit doppelten Frequenzen), Ausgang -> RZ_TOUT, dann jeder
    Frame doppelt nach out."""
    assert rz.GAIN == 3
    a = A(rz.M_RZ)
    # Phaser-Durchlauf je Kanal (0 = links, 4 = rechts): Zustand ab so, Koeffizient sa
    passes = ''.join(f'''
            lea     {rz.TMP:#x},a0
            movea.l #{RZ_TOUT:#x},a1{"""
            addq.l  #4,a1""" if c else ""}
            lea     128(a0),a4               ; 16 Frames
            move.l  {sa}(a3),d7
            movem.l {so}(a3),d2-d6
            jsr     {pass_at:#x}
            movem.l d2-d6,{so}(a3)''' for c, so, sa in ((0, 8, 0x30), (4, 28, 0x34)))
    asm(a, f'''
    RZ:     lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 56(sp),a0                ; params
            lea     {rz.RZP:#x},a1
            move.w  (a0),(a1)                ; Size
            move.l  #{rz.TONE << 8:#x},d1
            move.w  d1,2(a1)                 ; Tone fest
            pea     (a1)
            move.l  56(sp),-(sp)
            move.l  56(sp),-(sp)
            jsr     {rz.REVERB:#x}           ; Reverb der Firmware
            lea     12(sp),sp
            movea.l 48(sp),a0                ; out
            moveq   #15,d0
    sh:     move.l  (a0),d1                  ; Sample-and-Hold x2, Pegel x3 (gesaettigt)
            move.l  4(a0),d2
            move.l  d1,d3
            add.l   d1,d1
            sats.l  d1
            add.l   d3,d1
            sats.l  d1
            move.l  d2,d3
            add.l   d2,d2
            sats.l  d2
            add.l   d3,d2
            sats.l  d2
            move.l  d1,(a0)+
            move.l  d2,(a0)+
            move.l  d1,(a0)+
            move.l  d2,(a0)+
            subq.l  #1,d0
            bpl     sh
            movea.l 56(sp),a0
            mvz.w   2(a0),d0
            lsr.l   #8,d0                    ; Speed
            beq     done
            movea.l 48(sp),a0                ; jeder zweite Frame -> TMP (16 Frames); d0 (Speed) bleibt
            lea     {rz.TMP:#x},a1
            moveq   #15,d1
    cp:     move.l  (a0)+,(a1)+
            move.l  (a0)+,(a1)+
            addq.l  #8,a0
            subq.l  #1,d1
            bpl     cp
            move.l  d0,d2
            muls.l  d0,d2
            moveq   #{rz.SPD_K},d3
            muls.l  d3,d2
            addi.l  #{rz.SPD_0:#x},d2
            lsl.l   #5,d2                    ; LFO-Schritt
            movea.l #{rz.FB:#x},a2
            lea     {rz.PSTATE2:#x},a3
            move.l  4(a3),d0
            cmpi.l  #{fx.PMAGIC:#x},d0
            beq     ok
            movea.l a3,a0                    ; Zustand erstmals leeren
            moveq   #11,d0
    cl:     clr.l   (a0)+
            subq.l  #1,d0
            bpl     cl
            move.l  #{fx.PMAGIC:#x},d0
            move.l  d0,4(a3)
    ok:     move.l  (a3),d0
            add.l   d2,d0
            move.l  d0,(a3)                  ; LFO-Phase
            jsr     {coef_at:#x}
            move.l  d7,48(a3)                ; Koeffizient links
            move.l  (a3),d0
            addi.l  #0x80000000,d0
            jsr     {coef_at:#x}
            move.l  d7,52(a3)                ; Koeffizient rechts (Phase + 180 Grad){passes}
            lea     {RZ_TOUT:#x},a0          ; jeder Ausgangs-Frame zweimal nach out
            movea.l 48(sp),a1
            moveq   #15,d1
    ex:     move.l  (a0)+,d2
            move.l  (a0)+,d3
            move.l  d2,(a1)+
            move.l  d3,(a1)+
            move.l  d2,(a1)+
            move.l  d3,(a1)+
            subq.l  #1,d1
            bpl     ex
    done:   movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ''')
    code = adone(a); check_cf(code, rz.M_RZ)
    return code, a.lab['RZ']


def build_razer2():
    P, _ = ph.phaser_opts()
    rz0, _ = build_rz2(P['p_addr'], 0)
    coef_at = (rz.M_RZ + len(rz0) + 3) & ~3
    old = (rz.FMIN, rz.FMAX)
    rz.FMIN, rz.FMAX = 2 * old[0], 2 * old[1]                 # 24 kHz: tan(pi f / 24k) = tan(pi 2f / 48k)
    try:
        coef, coef_addr = rz.build_coef2(coef_at)
    finally:
        rz.FMIN, rz.FMAX = old
    code, rz_addr = build_rz2(P['p_addr'], coef_addr)
    assert len(code) == len(rz0)
    blob = code + bytes(coef_at - rz.M_RZ - len(code)) + coef
    return dict(blob=blob, rz=rz_addr, coef=coef_addr, pass_at=P['p_addr'])


def build_dsp():
    ch.configure()
    c3.MODE = RMODE                         # v2: Modus aus dem RAM-Spiegel statt aus dem Einstellungsblock
    setup, loop, tap = c3.build()
    tap = tap + bytes(c3.M_TAB - c3.M_TAP - len(tap)) + c3.table()
    P = ph.build_phaser()
    Z = build_razer2()                      # smp22: Phaser in RAZR mit halber Rate
    return dict(setup=setup, loop=loop, tap=tap, P=P, Z=Z)


def build_tables(img):
    """Texte der Modi 1..4 (M_STR), F0 (Anzeige 0..127) am Anfang von M_TAB. Die Tabelle selbst (8 Zeilen zu 8 Zeigern
    [Name27, Kurz27, Name39, Kurz39, Name40, Kurz40, Fn39, Fn40], Zeile 0 = Original aus dem Image) liegt seit smp9 in der
    Nutzlast (rows(at)), die Texte der Modi 5..7 dahinter."""
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(C.DESC(27) + 0x2C), rd(C.DESC(27) + 0x34), rd(C.DESC(39) + 0x2C), rd(C.DESC(39) + 0x34),
            rd(C.DESC(40) + 0x2C), rd(C.DESC(40) + 0x34)]
    strs = b''; pool = {}
    def put(s):
        nonlocal strs
        if s not in pool: pool[s] = M_STR + len(strs); strs += s + b'\0'
        return pool[s]
    f0_at = M_TAB
    low = {m: [put(x) for x in ROWS[m]] for m in range(1, 5)}
    def rows(at):
        extra = b''; ptr = {}
        tail = at + 32 * (RMAX + 1)
        for m in range(5, RMAX + 1):
            ptr[m] = []
            for x in ROWS[m]:
                ptr[m].append(tail + len(extra)); extra += x + b'\0' + (b'\0' if (m, x) == (5, ROWS[5][0]) else b'')   # Platz fuer die EMAC-Probe (g2_reverbs)
        tab = struct.pack('>8I', *orig, cf.F39_ORIG, cf.F40_ORIG)
        for m in range(1, RMAX + 1):
            tab += struct.pack('>8I', *(low[m] if m < 5 else ptr[m]), f0_at, f0_at)
        return tab + extra + bytes(-len(extra) % 4)
    return strs, cf.F0_code(f0_at), rows


def build_ui(dsp, ptab, rvb):
    a = A(M_UI)
    asm(a, f'''
    ; ---------------- R: statt jsr Reverb im Mixer (Stapel: ret, out, in, params)
    R:      bsr     RSYNC
            moveq   #0,d1
            move.b  {RMODE:#x},d1
            cmpi.l  #5,d1
            bcc     rvb                      ; Hall / Room / Plate
            moveq   #-1,d0
            move.l  d0,{RV.ST + RV.V['SMODE']:#x}   ; Rueckkehr dorthin beginnt leer
            tst.l   d1
            bne     rc
            jmp     {REVERB:#x}              ; 0: Reverb der Firmware
    rvb:    jmp     {rvb:#x}
    rc:     cmpi.l  #3,d1
            bne     r4
            jmp     {dsp['P']['ph']:#x}      ; Phaser
    r4:     cmpi.l  #4,d1
            bne     rch
            jmp     {dsp['Z']['rz']:#x}      ; RAZR
    rch:    lea     {STATE + 8:#x},a0        ; Chorus I / II: Ring beim ersten Mal leeren (Magic)
            move.l  (a0),d0
            cmpi.l  #{CMAGIC:#x},d0
            beq     go
            lea     {STATE:#x},a0
            move.l  #2060,d0
    cl:     clr.l   (a0)+
            subq.l  #1,d0
            bne     cl
            move.l  #{CMAGIC:#x},d0
            lea     {STATE + 8:#x},a0
            move.l  d0,(a0)
    go:     jmp     {M_SETUP:#x}
    ; ---------------- RSYNC: Pattern-Byte -> RMODE, dann Namen (veraendert d0, d1, a0, a1)
    RSYNC:  moveq   #0,d1
            move.l  {C.CUR_PAT:#x},d0
            beq     s0
            movea.l d0,a0
            mvz.b   {C.HDR + C.P_RFX}(a0),d1
            cmpi.l  #{RMAX},d1
            bls     s0
            moveq   #0,d1                    ; ungueltig -> Reverb
    s0:     move.b  d1,{RMODE:#x}
    ; N: Namen + Anzeigefunktionen nach d1
            move.l  d1,d0
            lsl.l   #5,d0
            lea     {ptab:#x},a1
            adda.l  d0,a1
            lea     {C.DTD(27) + 0x2C:#x},a0 ; smp18: Kopie der Deskriptor-Tabelle (Core)
            move.l  (a1)+,(a0)
            move.l  (a1)+,8(a0)
            lea     {C.DTD(39) + 0x2C:#x},a0
            move.l  (a1)+,(a0)
            move.l  (a1)+,8(a0)
            lea     56(a0),a0
            move.l  (a1)+,(a0)
            move.l  (a1)+,8(a0)
            move.l  (a1)+,{cf.FN39:#x}
            move.l  (a1)+,{cf.FN40:#x}
            rts
    ''')
    code = adone(a); check_cf(code, M_UI)
    return code, dict(a.lab)


def build_rfxh(org, rsync):
    a = A(org)
    asm(a, f'''
    ; ---------------- RFXH (Core-Slot): TRACK + Reverb Size -> Effektwahl
    RFXH:   move.l  4(a2),d0
            cmpi.l  #{C.ENC_RSIZE},d0
            bne     no
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     no
            move.l  {C.CUR_PAT:#x},d0
            beq     no
            movea.l d0,a0
            lea     {C.HDR + C.P_RFX}(a0),a0
            moveq   #{RMAX},d1
            lea     {rsync:#x},a1
            jmp     {core.sym()['MODESW']:#x}  ; liefert d0 = 2
    no:     moveq   #0,d0
            rts
    ''')
    code = adone(a); check_cf(code, org)
    return code, dict(a.lab)


def build(img):
    D = build_dsp()
    strs, f0, rows = build_tables(img)
    blob, rl_, sizes = RV.payload(RMODE, rows)
    ui, lab = build_ui(D, rl_['PTAB'], rl_['RVB'])
    org = (M_TAB + len(f0) + 1) & ~1
    rc, rl = build_rfxh(org, lab['RSYNC'])
    tab = f0 + bytes(org - M_TAB - len(f0)) + rc; lab.update(rl)
    P, Z = D['P'], D['Z']
    parts = {M_SETUP: D['setup'], M_LOOP: D['loop'], M_TAP: D['tap'], M_STR: strs, M_TAB: tab, M_UI: ui,
             ph.M_PP: P['pp'], ph.M_PT: P['pt'], ph.M_PSA: P['psa'], ph.M_PSB: P['psb'], rz.M_RZ: Z['blob']}
    lab.update(phaser=P['ph'], razer=Z['rz'], setup=M_SETUP, f0=M_TAB, tab=rl_['PTAB'],
               **{k: rl_[k] for k in ('RVB', 'RVEND', 'PRG5', 'PRG6', 'PRG7', 'PTAB', 'OP_HAD', 'OP_AP', 'OP_FWR', 'OP_SHF')})
    return parts, lab, blob, sizes


def tweak(img):
    """img = Stock-Image; 'old' gegen Stock + Core."""
    base = apply(img, core.tweak(img))
    parts, lab, blob, sizes = build(img)
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(R_HOOK, jsr(REVERB), jsr(lab['R']))
    off, room = C.PAY_SLOT['reverb-fx']
    assert len(base) == C.IMG_END - BASE + C.PAYSZ and len(blob) <= room, (hex(len(base)), len(blob))
    W.put(C.IMG_END + off, blob)                             # eigener Platz in der Nutzlast des Cores
    core.slot_write(W, 'reverb-fx', lab['RFXH'])
    return patch('reverb-fx', 5, 'Reverb FX: Chorus I / II, Phaser, RAZR, Hall, Room, Plate',
                 ["TRACK + Reverb Size: Reverb -> Chorus I -> Chorus II -> Phaser -> RAZR -> Hall -> Room -> Plate. Stored per pattern (header byte 52).",
                  "Hall / Room / Plate: own algorithms in the style of the Dragonfly Reverbs (no code taken); Size = decay, Tone = damping.",
                  f"Code and tables ({len(blob)} B) live in the core's payload slot at {RV.PAY:#x}.",
                  "Erzeugt von v2/g2_reverbfx.py und v2/g2_reverbs.py (Klang: v2/rv_algos.py)."], W, requires=['core'],
                 hooks=[f"{R_HOOK:#x}"],
                 memory=[{"va": f"{STATE:#x}", "size": 0x2030, "ram": True, "use": "chorus state + ring"},
                         {"va": f"{ph.PSTATE:#x}", "size": 0x38, "ram": True, "use": "phaser state"},
                         {"va": f"{rz.PSTATE2:#x}", "size": 0x38, "ram": True, "use": "RAZR phaser state"},
                         {"va": f"{rz.RZP:#x}", "size": 4, "ram": True, "use": "RAZR reverb parameters"},
                         {"va": f"{rz.TMP:#x}", "size": 256, "ram": True, "use": "RAZR buffer"},
                         {"va": f"{RMODE:#x}", "size": 1, "ram": True, "use": "mode mirror"},
                         {"va": f"{RV.PAY:#x}", "size": len(blob), "ram": True, "use": "payload (code, tables), copied at start"},
                         {"va": f"{RV.ST:#x}", "size": 0x400, "ram": True, "use": "Hall / Room / Plate state"},
                         {"va": f"{RV.RINGS:#x}", "size": max(sizes.values()), "ram": True, "use": "Hall / Room / Plate delay lines"}],
                 pattern=f"header byte {C.P_RFX}: 0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR, 5 Hall, 6 Room, 7 Plate",
                 symbols={k: f"{v:#x}" for k, v in lab.items()},
                 params={"slot": C.SLOT['reverb-fx'], "rmode": f"{RMODE:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, blob, sizes = build(stock())
    print(len(blob), {f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items()})
