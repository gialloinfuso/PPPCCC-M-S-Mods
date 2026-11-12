#!/usr/bin/env python3
"""Mod 'groove' (v2): Grooves + Humanize. Braucht nur 'core'.
FUNC + Swing: Groove (Swing, Boom Bap, Disco, Dancehall 1/2, Hip Hop, Jazz Rock, Perc 1-3, Soca; 4 Rastungen je Stufe, Popup
  'Groove' + Name). Swing je Track = Staerke. SETTINGS + Swing = Humanize Zeit, MACHINE + Swing = Humanize Velocity
  (0..100, ausgewaehlter Track; mit TRACK alle Tracks: relativ, oder absolut wenn control-mode es so eingestellt hat).
  MACHINE oeffnet sein Menue beim Loslassen.
Gespeichert im Pattern: Kopf-Byte 55 = Groove (0..10, ungueltig = 0), 40..45 / 46..51 = Humanize Zeit / Velocity
  (Kopieren beim Laden und Loeschen fuer neue Patterns macht der Core).
Klang wie v1 (gen_groove_113): Haken G im Ereignisbau 0x40054af8; G liest den Groove jetzt aus dem Pattern-Kopf (a3 = B).
GRH (Core-Slot 4): FUNC / SETTINGS / MACHINE + Swing. MK (Haken 0x4001ca1e): MACHINE-Menue beim Loslassen.
Speicher: 0x4014b85c (G + Humanize), 0x4014d74c (RND + HUM), 0x401542f8 / 0x401548b4 / 0x4015b8f8 / 0x4016f8c8 (T + Tabellen),
  0x40171f30 (GRH, MK), 0x4015f38c (Texte). RAM: MPEND = VARS+36.
Aufruf: g2_groove.py [out.json]
"""
import collections, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import gen_groove_113 as gg
from cfasm import asm, done as adone

HOOK, BACK, ORIG = gg.HOOK, gg.BACK, gg.ORIG
M_G, M_GD, M_T, M_T2, M_T3, M_T4, M_K = gg.M_G, gg.M_GD, gg.M_T, gg.M_T2, gg.M_T3, gg.M_T4, gg.M_K
M_H2 = 0x40186168                             # smp26: zweiter Teil von HUM (104 B)
M_TX = 0x4015F38C                             # Texte (48x22, 192 B)
SIZE = dict(gg.SIZE); SIZE[M_TX] = 192; SIZE[M_H2] = 104
HMAX, HK = gg.HMAX, gg.HK
# smp8 (02.11.2026): von den alten Grooves bleiben Boom Bap und Disco, dazu eigene Grooves (grooves/grooves.json).
# Tabellen mit eigener Laenge (16 / 32 / 64 Steps): [Laenge - 1] [Versatz x L] [Velocity x L].
GROOVES = ['Boom Bap', 'Disco', 'Dancehall 1', 'Dancehall 2', 'Hip Hop', 'Jazz Rock', 'Perc 1', 'Perc 2', 'Perc 3',
           'Soca']
NAMES = ["Swing", "Boom Bap", "Disco", "Dancehall 1", "Dancehall 2", "Hip Hop", "Jazz Rock", "Perc 1", "Perc 2", "Perc 3",
         "Soca"]
GMAX = len(GROOVES)
assert len(NAMES) == GMAX + 1
MPEND = C.VARS + C.V_MPEND
M_HOOK, M_ORIG = gg.M_HOOK, gg.M_ORIG
HDR, HOFF, HOFF_V = C.HDR, C.P_HUM_T, C.P_HUM_V - C.P_HUM_T
assert (HDR, HOFF, HOFF_V) == (gg.HDR, gg.HOFF, gg.HOFF_V)
TXT = {'groove': "Groove", 'humt': "Hum Time", 'humv': "Hum Vel", 'track': "Track", 'all': "All"}


def build_g(t_addr, rnd):
    """wie gen_groove_113.build_g2, Groove aus dem Pattern-Kopf (move.b HDR+55(a3),d7 statt move.b GMODE,d7)."""
    a = A(M_G)
    asm(a, f'''
    G:      moveq   #0,d7
            move.b  {HDR + C.P_GROOVE}(a3),d7  ; Groove des Patterns
            tst.l   d7
            bne     g1
            orig    {HOOK:#x},6              ; Original-Swing: verschobene Befehle (aus dem Image)
            beq     HUM
            orig    {HOOK + 8:#x},12
            bra     HUM
    g1:     cmpi.l  #{GMAX},d7
            bhi     HUM
            jmp     {t_addr:#x}
    ; ---------------- HUM: Humanize (Zeit d5, Velocity 52(sp)) fuer Track d6
    HUM:    moveq   #5,d7
            cmp.l   d6,d7
            bcs     ret
            lea     {HDR + HOFF}(a3),a0
            moveq   #0,d0
            move.b  0(a0,d6.l),d0            ; Zeit-Menge
            moveq   #0,d1
            move.b  {HOFF_V}(a0,d6.l),d1     ; Velocity-Menge
            cmpi.l  #{HMAX},d0
            bls     a1
            moveq   #0,d0
    a1:     cmpi.l  #{HMAX},d1
            bls     a2
            moveq   #0,d1
    a2:     moveq   #{HK},d7
            muls.l  d7,d0
            asr.l   #7,d0
            muls.l  d7,d1
            asr.l   #7,d1
            movea.l d1,a0
            move.l  d0,d7
            or.l    d1,d7
            beq     ret
            mvs.b   62(sp),d1
            orig    {HOOK + 10:#x},8         ; Faktor*12*st (Rechnung der Firmware, aus dem Image)
            move.l  {rnd:#x},d7              ; Zufall: rnd = rnd*1664525 + 1013904223
            move.l  #1664525,d0
            muls.l  d0,d7
            addi.l  #1013904223,d7
            move.l  d7,{rnd:#x}
            move.l  d7,d0
            swap    d0
            andi.l  #0x7fff,d0
            subi.l  #0x4000,d0
            muls.l  d1,d0
            asr.l   #8,d0
            asr.l   #8,d0
            asr.l   #1,d0
            add.l   d0,d5                    ; Zeit
            move.l  d7,d0
            lsr.l   #1,d0
            andi.l  #0x7fff,d0
            subi.l  #0x4000,d0
            move.l  a0,d1
            muls.l  d1,d0
            move.l  52(sp),d1
            tst.l   d1
            ble     ret
            muls.l  d1,d0
            move.l  d0,d7
            lsl.l   #2,d0
            add.l   d7,d0
            addi.l  #0x800000,d0
            moveq   #24,d7
            asr.l   d7,d0
            add.l   d0,d1                    ; Velocity, 1..127
            moveq   #1,d0
            cmp.l   d1,d0
            ble     v1
            move.l  d0,d1
    v1:     moveq   #127,d0
            cmp.l   d1,d0
            bge     v2
            move.l  d0,d1
    v2:     move.l  d1,52(sp)
    ret:    rts
    ''')
    code = adone(a); check_cf(code, M_G); assert len(code) <= SIZE[M_G], len(code)
    return code, dict(a.lab)


def build_hum(org, txt):
    """HUM (d0 = 0 Zeit / 6 Velocity; a2 = Ereignis) -> d0 = 1. smp26: mit TRACK nur die Spuren der Control-All-Auswahl
    (CA_SEL, control-mode) und die aktive Spur."""
    cs = core.sym()
    text = f"""
    HUM:    lea     -20(sp),sp
            movem.l d2-d5/a2,(sp)
            move.l  d0,d5
            moveq   #{C.KEY_SET},d0
            tst.l   d5
            beq     k1
            moveq   #{C.KEY_MACH},d0
    k1:     jsr     {cs['GEST']:#x}
            clr.l   {MPEND:#x}
            mvs.b   8(a2),d3
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            move.l  d0,d4                    ; d4 = 0 ohne TRACK, sonst 0x40 | ausgenommene Spuren (CA_SEL)
            beq     k2
            mvz.b   {C.CA_SEL:#x},d4
            move.l  d4,d0
            andi.l  #0xc0,d0
            cmpi.l  #0x80,d0
            beq     k3
            moveq   #0,d4
    k3:     andi.l  #0x3f,d4
            ori.l   #0x40,d4
    k2:     jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_C:#x}
            addq.l  #8,sp
            moveq   #5,d1
            cmp.l   d0,d1
            bcs     hxj
            move.l  d0,d2
            movea.l {C.CUR_PAT:#x},a2
            move.l  a2,d1
            beq     hxj
            lea     {HDR + HOFF}(a2),a2
            adda.l  d5,a2
            moveq   #0,d1
    lp:     cmp.l   d1,d2
            beq     do
            tst.l   d4
            beq     nt
            btst    d1,d4
            bne     nt
    do:     moveq   #0,d0
            move.b  0(a2,d1.l),d0
            cmpi.l  #{HMAX},d0
            bls     h0
            moveq   #0,d0
    h0:     add.l   d3,d0
            bpl     h1
            moveq   #0,d0
    h1:     cmpi.l  #{HMAX},d0
            ble     h2
            moveq   #{HMAX},d0
    h2:     move.b  d0,0(a2,d1.l)
    nt:     addq.l  #1,d1
            moveq   #6,d0
            cmp.l   d0,d1
            bne     lp
            moveq   #0,d1
            move.b  0(a2,d2.l),d1
            tst.l   d4
            beq     abj
            jmp     HUM2
    abj:    jmp     ab
    hxj:    jmp     hx
    ; HUM2: Rest (CONTROL ALL absolut, Popup) in eigener Maske
    HUM2:   mvz.b   {C.CTRL_MODE:#x},d0
            cmpi.l  #{C.CTRL_ABS},d0
            bne     ab
            moveq   #5,d0
    cp:     cmp.l   d0,d2
            beq     cpw
            btst    d0,d4
            bne     cpx
    cpw:    move.b  d1,0(a2,d0.l)
    cpx:    subq.l  #1,d0
            bpl     cp
    ab:     lea     {txt['humt']:#x},a0
            tst.l   d5
            beq     s1
            lea     {txt['humv']:#x},a0
    s1:     lea     {txt['track']:#x},a1
            tst.l   d4
            beq     s2
            lea     {txt['all']:#x},a1
    s2:     moveq   #{C.OV_NUM},d0
            jsr     {cs['OVS']:#x}
    hx:     movem.l (sp),d2-d5/a2
            lea     20(sp),sp
            moveq   #1,d0
            rts
"""
    t1, t2 = text.split('    ; HUM2:')
    t2 = '    ; HUM2:' + t2
    lab = collections.defaultdict(int)
    for _ in range(3):
        a1 = A(org); asm(a1, t1, lab)
        a2 = A(M_H2); asm(a2, t2, lab)
        lab = collections.defaultdict(int, {**a1.lab, **a2.lab})
    return adone(a1, dict(lab)), dict(lab), adone(a2, dict(lab))


def build_k(hum, txt, gnames):
    """GRH (Core-Slot) + MK + Texte in M_K."""
    cs = core.sym()
    a = A(M_K)
    asm(a, f'''
    ; ---------------- GRH: Encoder-Slot; Swing mit SETTINGS / MACHINE / FUNC
    GRH:    move.l  4(a2),d0
            cmpi.l  #{C.ENC_SWING},d0
            bne     no
            mvs.b   8(a2),d0
            beq     no
            pea     {C.KEY_SET}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     nf
            moveq   #0,d0                    ; SETTINGS: Humanize Zeit
            jmp     {hum:#x}
    nf:     pea     {C.KEY_MACH}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     nm
            moveq   #{HOFF_V},d0             ; MACHINE: Humanize Velocity
            jmp     {hum:#x}
    nm:     pea     {C.KEY_FUNC}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            bne     grv
    no:     moveq   #0,d0
            rts
    ; ---- FUNC + Swing: Groove (Pattern-Byte 55)
    grv:    lea     -8(sp),sp
            movem.l d4-d5,(sp)
            mvs.b   8(a2),d4
            move.l  {C.CUR_PAT:#x},d5
            beq     gsk
            addi.l  #{HDR + C.P_GROOVE},d5   ; auch Ziel-Kennung fuer SLOW
            jsr     {cs['SLOW']:#x}
            tst.l   d0
            beq     gsk
            movea.l d5,a0
            mvz.b   (a0),d0
            cmpi.l  #{GMAX},d0
            bls     g0
            moveq   #0,d0
    g0:     tst.l   d4
            bmi     gdn
            cmpi.l  #{GMAX},d0
            beq     gsh
            addq.l  #1,d0
            bra     gst
    gdn:    tst.l   d0
            beq     gsh
            subq.l  #1,d0
    gst:    move.b  d0,(a0)
    gsh:    lsl.l   #2,d0                    ; d1 = Name[Groove]
            lea     {gnames:#x},a1
            move.l  0(a1,d0.l),d1
            lea     {txt['groove']:#x},a0
            suba.l  a1,a1
            moveq   #{C.OV_TEXT},d0
            jsr     {cs['OVS']:#x}
    gsk:    movem.l (sp),d4-d5
            lea     8(sp),sp
            moveq   #1,d0
            rts
    ; ---------------- MK: MACHINE im Hauptbildschirm (wie v1)
    MK:     movea.l d3,a0
            move.l  16(a0),d0
            moveq   #9,d1
            and.l   d1,d0
            subq.l  #1,d0
            bne     mr
            moveq   #1,d0
            move.l  d0,{MPEND:#x}
            addq.l  #4,sp
            jmp     {core.K_DONE:#x}
    mr:     move.l  16(a0),d0
            btst.l  #4,d0
            beq     mn
            tst.l   {MPEND:#x}
            beq     mn
            clr.l   {MPEND:#x}
            moveq   #1,d0
            rts
    mn:     moveq   #0,d0
            rts
    ''')
    code = adone(a); check_cf(code, M_K)
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


def gtable(name):
    """Groove <name> aus grooves/grooves.json -> (Bytes [L - 1, Versatz x L, Velocity x L], Groove)."""
    import os
    _, g = gg.table(name)
    L = g['steps']; assert L in (16, 32, 64) and g['off'][:L] * (64 // L) == g['off'] and g['vel'][:L] * (64 // L) == g['vel']
    return bytes([L - 1]) + struct.pack('%db' % L, *g['off'][:L]) + bytes(g['vel'][:L]), g


def build_t(S):
    """T (Tabellen-Grooves 1..GMAX): wie gen_groove_113.build_t, aber Tabellen mit eigener Laenge (Step & (L - 1))."""
    a = A(M_T)
    asm(a, f'''
    T:      cmpi.l  #{GMAX},d7
            bhi     out
            move.l  d2,-(sp)                 ; Velocity jetzt bei 0x38(sp)
            dc.w    0x3208                   ; move.w a0,d1  Faktor der Spurgeschwindigkeit
            subq.l  #1,d7
            lsl.l   #2,d7
            lea     PTRS,a0
            movea.l 0(a0,d7.l),a0
            mvz.b   (a0),d2                  ; L - 1
            move.l  d3,d7
            and.l   d2,d7
            adda.l  d7,a0
            mvs.b   2(a0,d2.l),d7            ; Groove-Velocity g
            mvs.b   1(a0),d2                 ; Versatz (1/256 Step)
            muls.l  d0,d2
            muls.l  d1,d2
            move.l  d2,d1
            lsl.l   #2,d2
            add.l   d1,d2
            asr.l   #6,d2
            add.l   d2,d5
            moveq   #127,d1
            sub.l   d7,d1
            muls.l  d0,d1                    ; (127 - g) * Swing
            move.l  0x38(sp),d2
            tst.l   d2
            ble     done
            muls.l  d2,d1
            move.l  #165,d7
            muls.l  d7,d1
            moveq   #20,d7
            asr.l   d7,d1
            sub.l   d1,d2
            moveq   #1,d1
            cmp.l   d2,d1
            ble     vok
            move.l  d1,d2
    vok:    move.l  d2,0x38(sp)
    done:   move.l  (sp)+,d2
    out:    jmp     {S['HUM']}
            dc.w    0
    PTRS:
    ''')
    code = adone(a); check_cf(code, M_T)
    return code, dict(a.lab)


def build():
    tabs = [gtable(n) for n in GROOVES]
    rnd = M_GD
    gc0, gl0 = build_g(0, rnd)
    tc, tlab = build_t(dict(HUM=gl0['HUM']))
    ptrs_at = tlab['PTRS']; assert ptrs_at % 4 == 0
    # Ablage: je Maske der Reihe nach, was passt (64er zuerst)
    room = {M_T: [ptrs_at + 4 * GMAX, M_T + SIZE[M_T]], M_T2: [M_T2, M_T2 + SIZE[M_T2]], M_T3: [M_T3, M_T3 + SIZE[M_T3]],
            M_T4: [M_T4, M_T4 + SIZE[M_T4]]}
    blob = {va: bytearray() for va in room}; place = [None] * GMAX
    for i in sorted(range(GMAX), key=lambda i: -len(tabs[i][0])):
        t = tabs[i][0]
        va = next(v for v in (M_T2, M_T3, M_T4, M_T) if room[v][0] + len(t) <= room[v][1])
        place[i] = room[va][0]; blob[va] += t; room[va][0] += len(t)
    tdata = bytes(tc) + struct.pack('>%dI' % GMAX, *place) + bytes(blob[M_T])
    t2, t3, t4 = bytes(blob[M_T2]), bytes(blob[M_T3]), bytes(blob[M_T4])
    gc, gl = build_g(tlab['T'], rnd)
    assert gl['HUM'] == gl0['HUM']
    # M_K: Code, dann Texte; M_GD: RND (8 B) + HUM
    tblob, txt, gnames = texts(M_TX)
    assert len(tblob) <= SIZE[M_TX], len(tblob)
    hum, hl, hum2 = build_hum(M_GD + 8, txt)
    kc, kl = build_k(hl['HUM'], txt, gnames)
    kblob = kc
    data = struct.pack('>I', 0x1234567) + bytes(4) + hum
    parts = {M_G: gc, M_GD: data, M_T: tdata, M_T2: t2, M_T3: t3, M_T4: t4, M_K: kblob, M_TX: tblob, M_H2: hum2}
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
                         f"{C.P_GROOVE} groove 0..{GMAX}",
                 symbols={k: f"{v:#x}" for k, v in lab.items()},
                 params={"slot": C.SLOT['groove'], "gmax": GMAX, "hmax": HMAX, "hk": HK, "names": NAMES,
                         "tabs": [f"{x:#x}" for x in place]})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, _ = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items()})
