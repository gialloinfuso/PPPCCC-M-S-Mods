#!/usr/bin/env python3
"""Mod 'mono' (v2, Patch 18, smp18): 9. Maschine 'Mono', ein monophoner Synth im Stil von SH-101 / Minimoog / Pro-One / MS-20
(eigener Code). Braucht Core (Nutzlast, Deskriptor-Tabelle), Sampler und Strings (Maschinen 7 und 8).

Klang (je Spur, 48 kHz, Bloecke zu 32 Samples; Modell: mono_model.py, Konstanten mono_tables.py):
  COLOR = Welle: SAW, SQR, PWM, S+P (Saege + Rechteck), TRI (mit Wavefolding), SYNC (Hard Sync), DTN (zweite Saege
  verstimmt), RING (Saege x Sinus). SHAPE = Klangfarbe der Welle (SAW: Spitze abrunden, SQR: Pulsbreite 50..5 %, PWM:
  Mitte der Pulsbreite, S+P: Anteil Rechteck, TRI: Faltung, SYNC: Frequenz des Slaves 1..8, DTN: 0..30 Cent, RING:
  Verhaeltnis 0.5..4). SWEEP = Sub-Oszillator (Rechteck eine Oktave tiefer). CONTOUR = Drive (unsymmetrische Saettigung, nie
  ganz sauber). FUNC + PITCH = Glide (RC, bei jedem Trig vom letzten Ton), FUNC + CONTOUR = Noise.
  Unperfektheit: Drift je Oszillator (zwei langsame Sinus), Zufallsverstimmung je Anschlag, frei laufende Phasen, Sub mit
  eigener Drift, fester warmer Tiefpass, leiser Rauschteppich, DC-Sperre. Saegen bandbegrenzt (polyBLEP wie Vlvt; Sync mit
  BLEP am Ruecksetzen). Amp-Decay / VCA der Firmware (Attack des Cores wirkt).
Maschine: Grenzen 7 -> 8, 9 Positionen (Abstand 6), Tabelle Maschine -> Klangerzeugung mit 9 Eintraegen (Verweis 0x400a7dc4),
  Namen / update / render / Zeilen mit 9 Eintraegen, Satz 9 aus dem von TONE (66..69 -> 80..83), MACHINES-Bilder von TONE.
  Deskriptoren 80..85 in der Tabelle des Cores (80..83 Feld 6 / Maschine 8; 84 Glide k 24 und 85 Noise k 27 Feld 7 =
  allgemein wie Attack: ueberall anwendbar, wirken nur auf Mono), FUNC-Knoepfe ueber LKXT des Cores, Speichern ueber
  Sound-Slot 4 (Satz +80 / +81).
Speicher: Nutzlast-Platz 'mono', Zustand je Spur 0x431a0000 + 0x200 t.
Aufruf: g2_mono.py [out.json]
"""
import collections, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import g2_sampler as SM
import g2_strings as ST
import g2_dtab as DT
import mono_tables as MT
import cfemac as E
from cfasm import asm, done as adone

MACH = 8
NAME = 'Monom'                       # Name im MACHINES-Menue (Pip 04.11.: 'Monom', vorher 'Mono')
ICON_FILE = C.ROOT / 'v2' / 'art' / 'monom_klein.bmp'   # eigenes kleines Icon (Pip, 34 x 34); grosses Bild von TONE
OFF, ROOM = C.PAY_SLOT['mono']
ORG = C.PAY + OFF
DBASE, DN = C.DESC_SLOT['mono']
TONE_REC, TONE_D0, TONE_DEC = 5, 66, 65
K_GLIDE, K_NOISE = 24, 27
# (lang, kurz, Feld, Slot, Maximum, Default, Schluessel, Spender-Objekt)
KNOBS = (('Wave', 'WAVE', 6, 11, 0x700, 0, 40, 0), ('Timbre', 'TIMB', 6, 12, 0x7F00, 0x4000, 50, 67),
         ('Sub Osc', 'SUB', 6, 13, 0x7F00, 0, 60, 68), ('Drive', 'DRIV', 6, 14, 0x7F00, 0x1800, 70, 69),
         ('Glide', 'GLID', 7, K_GLIDE, 0x7F00, 0, 78, 64), ('Noise', 'NOIS', 7, K_NOISE, 0x7F00, 0, 79, 63))
FKNOBS = ((2, DBASE + 4), (7, DBASE + 5))             # FUNC + PITCH = Glide, FUNC + CONTOUR = Noise
B8 = ST.B7                                            # dieselben Grenzen wie bei Strings, jetzt 7 -> 8 (Positionen 8 -> 9)
STEP_AT, STEP_CK = 0x400A26E6, (2, None)              # addq.l #7,d4 (Abstand der Positionen) -> #6
MAP_REF = 0x400A7DC4                                  # lea 0x40118640 (Maschine -> Klangerzeugung) in der Stimmen-Schleife
MAP_OLD = 0x40118640
OBJ0 = DT.OBJ_BASE                                    # Anzeige-Objekt 0 ('Error', ungenutzt) -> Formatierer der Wellennamen
RAM, TSTR = 0x431A0000, 0x200
MAGIC = 0x4D4F4E31                                    # 'MON1' in der Stimme +0x70
OS = dict(A1=0x00, A2=0x20, S1=0x40, S2=0x60, SL=0x80, R2=0xA0)
T = dict(CUR=0xC0, RNG=0xC4, RND=0xC8, INIT=0xCC, O1A=0xD0, O1B=0xD4, O2A=0xD8, O2B=0xDC, SUBA=0xE0, SUBB=0xE4, PWM=0xE8,
         WAVE=0xEC, SH=0xF0, G88=0xF4, LPC=0xF8, NL=0xFC, DG8=0x100, MK=0x104, LP=0x108, DCX=0x10C, DCY=0x110,
         D1=0x114, D2=0x118, DS=0x11C, TMP=0x120)                     # TMP: 128 B (RING)
O = ST.O


def ck_step():
    import hashlib
    return (2, hashlib.sha256(bytes.fromhex('5e84')).hexdigest())


KW = dict(VOICE0=ST.VOICE0, VSTRIDE=ST.VSTRIDE, RAM=RAM, TSTR=TSTR, MAGIC=MAGIC, DECLUT=SM.DECLUT, AMPENV=SM.AMPENV, VCA=SM.VCA,
          INC0=ST.KW['INC0'], OBJ0=OBJ0, SPRINTF=SM.SPRINTF, NW=len(MT.WAVES),
          **{f'T_{k}': v for k, v in T.items()}, **{f'S_{k}': v for k, v in OS.items()}, **{f'O_{k}': v for k, v in O.items()},
          **{f'K_{k}': v for k, v in MT.C.items()})


def code_text(k):
    mimg3 = SM.mimg_text('MIMG3', MACH, 4, 'MBM', k['ST_MIMG'])
    drift = lambda nm, dst: f'''            move.l  {k[f"T_{nm}A"]}(a4),d0
            jsr     SINQ
            move.l  d0,d3
            move.l  {k[f"T_{nm}B"]}(a4),d0
            jsr     SINQ
            move.l  #{k[f"K_D{nm.lower()}A"]},d1
            mac     d3,d1,acc1
            move.l  #{k[f"K_D{nm.lower()}B"]},d1
            mac     d0,d1,acc1
            movclr  acc1,d0
            move.l  d0,{k[f"T_{dst}"]}(a4)
'''
    return f'''
    ; ================= Maschine 8: Saetze, Knopf-Vektor, MACHINES-Bild, Formatierer der Wellen
    RAT3:   move.l  4(sp),d0
            moveq   #9,d1
            cmp.l   d1,d0
            bne     ra1
            jmp     REC10
    ra1:    jmp     {k['ST_RAT']}
    ROF3:   move.l  4(sp),d0
            moveq   #8,d1
            cmp.l   d1,d0
            bne     ro1
            jmp     REC10
    ro1:    jmp     {k['ST_ROF']}
    REC10:  move.l  #WFMT,d0                 ; Anzeige-Objekt 0 (Spender von WAVE): Namen der Wellen, keine Sonderzeichnung
            move.l  d0,{OBJ0 + 32:#x}
            clr.l   {OBJ0 + 44:#x}
            pea     {DBASE}.w
            pea     {TONE_D0}.w
            pea     {TONE_REC}.w
            pea     R10
            jsr     {k['RBUILD']}
            lea     16(sp),sp
            rts
    KV3:    move.l  36(sp),d0
            movea.l 104(a2),a1
            moveq   #6,d1
            cmp.l   d1,d0
            blt     kv1
            lea     VEC9,a1
    kv1:    rts
{mimg3}
    ; Formatierer (8(sp) = Wert 8.8, 12(sp) = Puffer): Name der Welle ueber den sprintf der Firmware
    WFMT:   move.l  8(sp),d0
            addi.l  #0x80,d0
            asr.l   #8,d0
            bpl     wf1
            moveq   #0,d0
    wf1:    moveq   #{len(MT.WAVES) - 1},d1
            cmp.l   d1,d0
            ble     wf2
            move.l  d1,d0
    wf2:    lea     WNAMES,a0
            move.l  0(a0,d0.l*4),d0
            move.l  12(sp),d1
            move.l  d1,4(sp)
            move.l  d0,8(sp)
            jmp     {k['SPRINTF']}
    ; Sound-Slot 4: Satz +80 = Glide, +81 = Noise (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern)
    MH:     tst.l   d1
            bne     mh1
            mvz.b   80(a0),d0
            lsl.l   #8,d0
            move.w  d0,{20 + 2 * K_GLIDE}(a1)
            mvz.b   81(a0),d0
            lsl.l   #8,d0
            move.w  d0,{20 + 2 * K_NOISE}(a1)
            rts
    mh1:    move.b  {20 + 2 * K_GLIDE}(a1),d0
            move.b  d0,80(a0)
            move.b  {20 + 2 * K_NOISE}(a1),d0
            move.b  d0,81(a0)
            rts

    ; ================= Zustand der Spur (a2 Stimme -> a4); neu (Magie fehlt): leer, Phasen, Zufall, INIT
    MSTATE: move.l  a2,d0
            subi.l  #{k['VOICE0']},d0
            move.l  #{k['VSTRIDE']},d1
            divu.l  d1,d0
            move.l  d0,d2
            move.l  #{k['TSTR']},d1
            mulu.l  d1,d0
            addi.l  #{k['RAM']},d0
            movea.l d0,a4
            move.l  0x70(a2),d0
            cmpi.l  #{k['MAGIC']},d0
            bne     ms1
            rts
    ms1:    movea.l a4,a0
            move.l  #{TSTR // 4 - 1},d0
    ms2:    clr.l   (a0)+
            subq.l  #1,d0
            bpl     ms2
            move.l  #0x12345678,d0
            move.l  d0,{OS['A1'] + O['P']}(a4)
            move.l  #0x5A000000,d0
            move.l  d0,{OS['S1'] + O['P']}(a4)
            move.l  #0x03000000,d0
            move.l  d0,{OS['R2'] + O['P']}(a4)
            move.l  #0x9E3779B9,d0
            mulu.l  d2,d0
            addi.l  #0x2545F491,d0
            move.l  d0,{T['RNG']}(a4)
            moveq   #1,d0
            move.l  d0,{T['INIT']}(a4)
            move.l  #{k['MAGIC']},d0
            move.l  d0,0x70(a2)
            rts
    RAND:   move.l  {T['RNG']}(a4),d0
            move.l  #1664525,d1
            mulu.l  d1,d0
            addi.l  #1013904223,d0
            move.l  d0,{T['RNG']}(a4)
            rts

    ; ================= update[8] (pmod, Stimme, Parameter)
    MUPD:   lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 52(sp),a2
            movea.l 56(sp),a3
            mvs.b   36(a3),d0                ; Amp-Decay wie TONE; smp44: GATE (+0x24c, von der Stimmen-Schleife) bleibt wie bei TONE
            lea     {k['DECLUT']},a0
            move.l  0(a0,d0.l*4),d1
            move.l  d1,0x250(a2)
            jsr     MSTATE
            tst.l   0x38(a2)
            beq     mu1
            jsr     RAND                     ; Zufallsverstimmung je Anschlag
            clr.w   d0
            swap    d0
            move.l  #{k['K_RNDK']},d1
            mulu.l  d1,d0
            clr.w   d0
            swap    d0
            subi.l  #{k['K_RNDK'] >> 1},d0
            move.l  d0,{T['RND']}(a4)
    mu1:    mvs.w   20(a3),d0                ; Ziel-Ton (16.16 Halbtoene)
            subi.l  #0x4000,d0
            lsl.l   #8,d0
            mvs.w   34(a3),d1
            subi.l  #0x4000,d1
            lsl.l   #3,d1
            add.l   d1,d0
            add.l   48(sp),d0
            cmpi.l  #{12 << 16},d0
            bge     mu2
            move.l  #{12 << 16},d0
    mu2:    cmpi.l  #{108 << 16},d0
            ble     mu3
            move.l  #{108 << 16},d0
    mu3:    mvz.b   {2 * K_GLIDE}(a3),d1     ; Glide (RC)
            tst.l   {T['INIT']}(a4)
            bne     mg0
            tst.l   d1
            beq     mg0
            lea     GLT,a0
            move.l  0(a0,d1.l*4),d1
            move.l  {T['CUR']}(a4),d2
            move.l  d2,acc0
            sub.l   d2,d0
            mac     d1,d0,acc0
            movclr  acc0,d0
    mg0:    move.l  d0,{T['CUR']}(a4)
            clr.l   {T['INIT']}(a4)
            lea     {T['O1A']}(a4),a0        ; LFO-Phasen: Drift (6), PWM
            move.l  #{k['K_Ro1A']},d0
            add.l   d0,(a0)+
            move.l  #{k['K_Ro1B']},d0
            add.l   d0,(a0)+
            move.l  #{k['K_Ro2A']},d0
            add.l   d0,(a0)+
            move.l  #{k['K_Ro2B']},d0
            add.l   d0,(a0)+
            move.l  #{k['K_RsubA']},d0
            add.l   d0,(a0)+
            move.l  #{k['K_RsubB']},d0
            add.l   d0,(a0)+
            move.l  #{k['K_DPWM']},d0
            add.l   d0,(a0)+
{drift('O1', 'D1')}{drift('O2', 'D2')}{drift('SUB', 'DS')}            move.l  {T['CUR']}(a4),d7
            add.l   {T['RND']}(a4),d7        ; d7 = Grundton + Zufall
            mvz.w   22(a3),d0                ; Welle
            addi.l  #0x80,d0
            lsr.l   #8,d0
            moveq   #7,d1
            cmp.l   d1,d0
            bls     mw1
            move.l  d1,d0
    mw1:    move.l  d0,{T['WAVE']}(a4)
            mvz.b   24(a3),d6                ; SHAPE 0..127
            andi.l  #0x7f,d6
            move.l  d6,{T['SH']}(a4)
            jmp     MUPD2

    ; d0 = Ton (16.16) -> d0 = Schritt (0.32), hoechstens 0x7fffffff; zerstoert d1..d5 / a0
    INC:    tst.l   d0
            bpl     ic1
            moveq   #0,d0
    ic1:    cmpi.l  #{127 << 16},d0
            ble     ic2
            move.l  #{127 << 16},d0
    ic2:    move.l  #{12 << 16},d1
            move.l  d0,d2
            remu.l  d1,d3:d2
            divu.l  d1,d2
            move.l  d3,d4
            swap    d4
            andi.l  #0xffff,d4
            andi.l  #0xffff,d3
            lea     P12,a0
            move.l  0(a0,d4.l*4),d5
            move.l  4(a0,d4.l*4),d0
            sub.l   d5,d0
            mulu.l  d3,d0
            swap    d0
            andi.l  #0xffff,d0
            add.l   d0,d5
            move.l  #{k['INC0']},d4
            lsl.l   d2,d4
            jsr     MUL16
            move.l  d4,d0
            cmpi.l  #0x7fffffff,d0
            bls     ic3
            move.l  #0x7fffffff,d0
    ic3:    rts
    MUL16:  move.l  d4,d1
            clr.w   d1
            swap    d1
            mulu.l  d5,d1
            move.l  d4,d2
            andi.l  #0xffff,d2
            mulu.l  d5,d2
            clr.w   d2
            swap    d2
            add.l   d2,d1
            move.l  d1,d4
            rts
    ; a0 = Oszillator, d0 = Schritt: INC, KINV
    SETINC: move.l  d0,{O['INC']}(a0)
            clr.w   d0
            swap    d0
            moveq   #-1,d1
            divu.l  d0,d1
            move.l  d1,{O['KINV']}(a0)
            rts
    ; d0 = Phase -> d0 = sin (Q31), Tabelle 256 + 1 linear; zerstoert d1 / d2 / a0, acc3 leer
    SINQ:   move.l  d0,d1
            moveq   #24,d2
            lsr.l   d2,d1
            lea     SINT,a0
            lea     0(a0,d1.l*4),a0
            lsl.l   #8,d0
            lsr.l   #1,d0
            move.l  (a0)+,d1
            move.l  (a0),d2
            sub.l   d1,d2
            move.l  d1,acc3
            mac     d0,d2,acc3
            movclr  acc3,d0
            rts

    ; ---------------- update, Teil 2: Oszillatoren (d7 Grundton, d6 SHAPE, a3 Parameter, a4 Zustand)
    MUPD2:  move.l  d7,d0
            add.l   {T['D1']}(a4),d0
            jsr     INC
            move.l  d0,-(sp)                 ; inc1
            lea     {OS['A1']}(a4),a0
            jsr     SETINC
            move.l  {T['WAVE']}(a4),d5
            move.l  #{k['K_G0']},d0          ; A1: Saege fuer alle ausser TRI / SYNC (eigene Schleifen)
            moveq   #4,d1
            cmp.l   d1,d5
            beq     m21
            moveq   #5,d1
            cmp.l   d1,d5
            bne     m22
    m21:    moveq   #0,d0
    m22:    move.l  d0,{OS['A1'] + O['TG']}(a4)
            clr.l   {OS['A2'] + O['TG']}(a4)
            moveq   #1,d1
            cmp.l   d1,d5
            blt     m30
            moveq   #3,d1
            cmp.l   d1,d5
            bgt     m30
            move.l  (sp),d0                  ; SQR / PWM / S+P: A2 = Saege um off verschoben, Phase an A1 gebunden
            lea     {OS['A2']}(a4),a0
            jsr     SETINC
            moveq   #1,d1
            cmp.l   d1,d5
            bne     m24
            move.l  #{k['K_PWK']},d0         ; SQR: off = 0.5 - 0.45 s / 127
            mulu.l  d6,d0
            move.l  #0x80000000,d3
            sub.l   d0,d3
            move.l  #{k['K_MG0']},d0
            bra     m27
    m24:    moveq   #2,d1
            cmp.l   d1,d5
            bne     m26
            move.l  {T['PWM']}(a4),d0        ; PWM: off = 0.5 - 0.3 s / 127 + LFO, 5..95 %
            jsr     SINQ
            move.l  #{k['K_PWMD']},d1
            mac     d0,d1,acc0
            movclr  acc0,d0
            move.l  #{k['K_PCK']},d3
            mulu.l  d6,d3
            move.l  #0x80000000,d1
            sub.l   d3,d1
            add.l   d1,d0
            cmpi.l  #0x0CCCCCCD,d0
            bcc     m25
            move.l  #0x0CCCCCCD,d0
    m25:    cmpi.l  #0xF3333333,d0
            bls     m25b
            move.l  #0xF3333333,d0
    m25b:   move.l  d0,d3
            move.l  #{k['K_MG0']},d0
            bra     m27
    m26:    move.l  #0x80000000,d3           ; S+P: off = 0.5, Gewicht des Rechtecks -G0 s / 127
            move.l  #{k['K_SUBK']},d0
            mulu.l  d6,d0
            neg.l   d0
    m27:    move.l  d0,{OS['A2'] + O['TG']}(a4)
            add.l   {OS['A1'] + O['P']}(a4),d3
            move.l  d3,{OS['A2'] + O['P']}(a4)
            jmp     m40
    m30:    moveq   #6,d1
            cmp.l   d1,d5
            bne     m32
            move.l  d6,d0                    ; DTN: zweite Saege, +0..30 Cent, eigene Drift und Phase
            mulu.w  #155,d0
            add.l   d7,d0
            add.l   {T['D2']}(a4),d0
            jsr     INC
            lea     {OS['A2']}(a4),a0
            jsr     SETINC
            move.l  #{k['K_G0']},d0
            move.l  d0,{OS['A2'] + O['TG']}(a4)
            jmp     m40
    m32:    moveq   #5,d1
            cmp.l   d1,d5
            bne     m34
            move.l  (sp),d4                  ; SYNC: Slave = inc1 x (1 + 7 s / 127)
            move.l  d6,d5
            mulu.w  #3612,d5
            addi.l  #65536,d5
            jsr     MUL16
            move.l  d4,d0
            cmpi.l  #0x7fffffff,d0
            bls     m33
            move.l  #0x7fffffff,d0
    m33:    lea     {OS['SL']}(a4),a0
            jsr     SETINC
            jmp     m40
    m34:    moveq   #7,d1
            cmp.l   d1,d5
            bne     m40
            move.l  d7,d0                    ; RING: Sinus mit eigener Drift x (0.5 + 3.5 s / 127)
            add.l   {T['D2']}(a4),d0
            jsr     INC
            move.l  d0,d4
            move.l  d6,d5
            mulu.w  #1806,d5
            addi.l  #32768,d5
            jsr     MUL16
            move.l  d4,{OS['R2'] + O['INC']}(a4)
    m40:    addq.l  #4,sp
            jmp     MUPD3

    ; ---------------- update, Teil 3: Sub, Verstaerkungs-Rampen, Tiefpass, Rauschen, Drive, Faltung
    MUPD3:  move.l  d7,d0
            subi.l  #{12 << 16},d0
            add.l   {T['DS']}(a4),d0
            jsr     INC
            lea     {OS['S1']}(a4),a0
            jsr     SETINC
            lea     {OS['S2']}(a4),a0
            move.l  {OS['S1'] + O['INC']}(a4),d0
            jsr     SETINC
            move.l  {OS['S1'] + O['P']}(a4),d0
            addi.l  #0x80000000,d0
            move.l  d0,{OS['S2'] + O['P']}(a4)
            mvz.b   26(a3),d0                ; SWEEP = Sub-Pegel
            andi.l  #0x7f,d0
            move.l  #{k['K_SUBK']},d1
            mulu.l  d1,d0
            move.l  d0,{OS['S1'] + O['TG']}(a4)
            neg.l   d0
            move.l  d0,{OS['S2'] + O['TG']}(a4)
            lea     {OS['A1']}(a4),a0        ; DG = (TG - G) / 32 fuer A1, A2, S1, S2
            moveq   #3,d2
    m51:    move.l  {O['TG']}(a0),d0
            sub.l   {O['G']}(a0),d0
            asr.l   #5,d0
            move.l  d0,{O['DG']}(a0)
            lea     32(a0),a0
            subq.l  #1,d2
            bpl     m51
            move.l  #{k['K_WARM']},d0        ; Tiefpass: SAW = SHAPE, sonst fest warm
            tst.l   {T['WAVE']}(a4)
            bne     m52
            lea     SAWLP,a0
            move.l  0(a0,d6.l*4),d0
    m52:    move.l  d0,{T['LPC']}(a4)
            mvz.b   {2 * K_NOISE}(a3),d0     ; Rauschen
            andi.l  #0x7f,d0
            move.l  #{k['K_NOK']},d1
            mulu.l  d1,d0
            addi.l  #{k['K_NFL']},d0
            move.l  d0,{T['NL']}(a4)
            mvz.b   28(a3),d0                ; CONTOUR = Drive
            andi.l  #0x7f,d0
            lsl.l   #3,d0
            lea     DRVT,a0
            adda.l  d0,a0
            move.l  (a0)+,d0
            move.l  d0,{T['DG8']}(a4)
            move.l  (a0),d0
            move.l  d0,{T['MK']}(a4)
            move.l  d6,d0                    ; Faltung (TRI) 1 + s / 64
            lsl.l   #2,d0
            addi.l  #256,d0
            move.l  d0,{T['G88']}(a4)
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts

    ; ================= render[8] (Ausgang, Stimme)
    MRND:   lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 48(sp),a1
            movea.l 52(sp),a2
            jsr     MSTATE
            lea     128(a1),a6
    rz:     clr.l   (a1)+
            cmpa.l  a6,a1
            bne     rz
            move.l  {T['WAVE']}(a4),d0
            moveq   #4,d1
            cmp.l   d1,d0
            bne     rn1
            jsr     TRI
            bra     rn9
    rn1:    moveq   #5,d1
            cmp.l   d1,d0
            bne     rn2
            jsr     SYNC
            bra     rn9
    rn2:    moveq   #7,d1
            cmp.l   d1,d0
            bne     rn3
            jsr     RING
            bra     rn9
    rn3:    lea     {OS['A1']}(a4),a5
            jsr     OSC
    rn9:    lea     {OS['A2']}(a4),a5
            jsr     OSC
            lea     {OS['S1']}(a4),a5
            jsr     OSC
            lea     {OS['S2']}(a4),a5
            jsr     OSC
            jsr     MOUT
            move.l  a2,-(sp)
            jsr     {k['AMPENV']}
            move.l  a2,(sp)
            move.l  52(sp),-(sp)
            jsr     {k['VCA']}
            addq.l  #8,sp
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts

    ; Oszillator a5 auf den Block a6 - 128 .. a6 addieren (wie Vlvt: Saege q = p ^ 0x80000000, polyBLEP, 1 Sample verzoegert)
    OSC:    movea.l {O['G']}(a5),a0
            movea.l {O['DG']}(a5),a3
            move.l  a0,d0
            bne     oc1
            move.l  a3,d0
            bne     oc1
            move.l  {O['INC']}(a5),d0
            lsl.l   #5,d0
            add.l   {O['P']}(a5),d0
            move.l  d0,{O['P']}(a5)
            move.l  d0,{O['PREV']}(a5)
            clr.l   {O['PEND']}(a5)
            rts
    oc1:    movem.l (a5),d3-d7
            lea     -128(a6),a1
            tst.l   d7
            beq     ol
            add.l   d4,d3
            move.l  d6,d1
            add.l   d7,d1
            moveq   #0,d7
            mac     a0,d1,acc0
            move.l  d3,d6
            movclr  acc0,d2
            add.l   d2,(a1)+
            adda.l  a3,a0
    ol:     add.l   d4,d3
            bvs     ow
            mac     a0,d6,acc0
            move.l  d3,d6
            movclr  acc0,d2
            add.l   d2,(a1)+
            adda.l  a3,a0
            cmpa.l  a6,a1
            bne     ol
            bra     oe
    ow:     move.l  d3,d1
            eori.l  #0x80000000,d1
            clr.w   d1
            swap    d1
            mulu.l  d5,d1
            clr.w   d1
            swap    d1
            move.l  #0x10000,d2
            sub.l   d1,d2
            cmpi.l  #0xffff,d2
            bls     ow1
            move.l  #0xffff,d2
    ow1:    mulu.l  d2,d2
            lsr.l   #1,d2
            mulu.l  d1,d1
            lsr.l   #1,d1
            neg.l   d1
            add.l   d6,d1
            mac     a0,d1,acc0
            move.l  d3,d6
            movclr  acc0,d0
            add.l   d0,(a1)+
            adda.l  a3,a0
            cmpa.l  a6,a1
            bne     ow2
            move.l  d2,d7
            bra     oe
    ow2:    add.l   d4,d3
            move.l  d6,d1
            add.l   d2,d1
            mac     a0,d1,acc0
            move.l  d3,d6
            movclr  acc0,d0
            add.l   d0,(a1)+
            adda.l  a3,a0
            cmpa.l  a6,a1
            bne     ol
    oe:     movem.l d3-d7,(a5)
            move.l  {O['TG']}(a5),d0
            move.l  d0,{O['G']}(a5)
            rts

    ; TRI: Dreieck aus der Phase von A1, gefaltet ueber den Sinus (Phase = Dreieck x G88 / 2)
    TRI:    lea     -128(a6),a1
            move.l  {OS['A1'] + O['P']}(a4),d3
            move.l  {OS['A1'] + O['INC']}(a4),d4
            move.l  {T['G88']}(a4),d5
            move.l  #{k['K_G0']},d7
    tl:     add.l   d4,d3
            move.l  d3,d0
            bpl     tl1
            not.l   d0
    tl1:    add.l   d0,d0
            subi.l  #0x7fffffff,d0
            moveq   #11,d1
            asr.l   d1,d0
            muls.l  d5,d0
            lsl.l   #2,d0
            jsr     SINQ
            mac     d7,d0,acc0
            movclr  acc0,d1
            add.l   d1,(a1)+
            cmpa.l  a6,a1
            bne     tl
            move.l  d3,{OS['A1'] + O['P']}(a4)
            rts

    ; SYNC: Slave-Saege (SL, halbe Skala) mit polyBLEP an eigenen Umbruechen und am Ruecksetzen durch A1
    SYNC:   lea     -128(a6),a1
            move.l  {OS['A1'] + O['P']}(a4),d3
            move.l  {OS['A1'] + O['INC']}(a4),d4
            move.l  {OS['SL'] + O['P']}(a4),d5
            move.l  {OS['SL'] + O['INC']}(a4),d6
            movea.l {OS['SL'] + O['PREV']}(a4),a0
            movea.l {OS['SL'] + O['PEND']}(a4),a3
            move.l  #{(2 * MT.C['G0']) & 0xFFFFFFFF},d7
    sl:     move.l  a0,d0                    ; Wert = vorheriger + Rest
            add.l   a3,d0
            suba.l  a3,a3
            add.l   d4,d3                    ; Master
            svs     d2
            add.l   d6,d5                    ; Slave
            bvc     sl1
            move.l  d2,-(sp)
            move.l  d5,d1                    ; Umbruch des Slaves
            eori.l  #0x80000000,d1
            clr.w   d1
            swap    d1
            mulu.l  {OS['SL'] + O['KINV']}(a4),d1
            clr.w   d1
            swap    d1
            move.l  #0x10000,d2
            sub.l   d1,d2
            cmpi.l  #0xffff,d2
            bls     sw1
            move.l  #0xffff,d2
    sw1:    mulu.l  d2,d2
            lsr.l   #2,d2
            adda.l  d2,a3
            mulu.l  d1,d1
            lsr.l   #2,d1
            sub.l   d1,d0
            move.l  (sp)+,d2
    sl1:    tst.b   d2
            beq     sl2
            move.l  d0,-(sp)                 ; Ruecksetzen durch den Master
            move.l  d3,d1
            eori.l  #0x80000000,d1
            clr.w   d1
            swap    d1
            mulu.l  {OS['A1'] + O['KINV']}(a4),d1
            clr.w   d1
            swap    d1                       ; u
            move.l  d6,d2
            clr.w   d2
            swap    d2
            mulu.l  d1,d2                    ; us = (incs >> 16) u
            move.l  d5,d0
            sub.l   d2,d0
            asr.l   #1,d0                    ; vor / 2
            addi.l  #0x80000000,d2
            move.l  d2,d5                    ; neue Phase
            asr.l   #1,d2
            sub.l   d0,d2                    ; dh
            move.l  d1,d0
            mulu.l  d0,d0
            lsr.l   #1,d0                    ; u^2
            move.l  #0x10000,d3
            sub.l   d1,d3
            cmpi.l  #0xffff,d3
            bls     sm1
            move.l  #0xffff,d3
    sm1:    mulu.l  d3,d3
            lsr.l   #1,d3                    ; (1 - u)^2
            mac     d2,d0,acc1
            movclr  acc1,d0
            add.l   (sp)+,d0
            mac     d2,d3,acc1
            movclr  acc1,d1
            suba.l  d1,a3
            move.l  {OS['A1'] + O['P']}(a4),d3   ; Master-Phase wieder (d3 war Hilfsregister)
            add.l   d4,d3
    sl2:    move.l  d5,d1
            asr.l   #1,d1
            movea.l d1,a0
            mac     d7,d0,acc0
            movclr  acc0,d1
            add.l   d1,(a1)+
            move.l  d3,{OS['A1'] + O['P']}(a4)
            cmpa.l  a6,a1
            bne     sl
            move.l  d5,{OS['SL'] + O['P']}(a4)
            move.l  a0,{OS['SL'] + O['PREV']}(a4)
            move.l  a3,{OS['SL'] + O['PEND']}(a4)
            rts

    ; RING: A1 (Saege, G0) in den Puffer TMP, dann Block += TMP x sin(R2)
    RING:   move.l  a6,-(sp)
            lea     {T['TMP']}(a4),a1
            lea     128(a1),a6
    rg0:    clr.l   (a1)+
            cmpa.l  a6,a1
            bne     rg0
            lea     {OS['A1']}(a4),a5
            jsr     OSC
            movea.l (sp)+,a6
            lea     -128(a6),a1
            lea     {T['TMP']}(a4),a5
            move.l  {OS['R2'] + O['P']}(a4),d3
            move.l  {OS['R2'] + O['INC']}(a4),d4
    rg1:    add.l   d4,d3
            move.l  d3,d0
            jsr     SINQ
            move.l  (a5)+,d1
            mac     d1,d0,acc0
            movclr  acc0,d1
            add.l   d1,(a1)+
            cmpa.l  a6,a1
            bne     rg1
            move.l  d3,{OS['R2'] + O['P']}(a4)
            rts

    ; Ausgang: halbe Skala + Rauschen, warmer Tiefpass, unsymmetrische Saettigung (tanh-Tabelle), Ausgleich, DC-Sperre, x2
    MOUT:   lea     -128(a6),a1
            move.l  {T['LP']}(a4),d3
            move.l  {T['DCX']}(a4),d4
            move.l  {T['DCY']}(a4),d5
            move.l  {T['RNG']}(a4),d6
            move.l  {T['LPC']}(a4),d7
            movea.l {T['NL']}(a4),a3
            movea.l {T['DG8']}(a4),a5
    mo:     move.l  (a1),d0
            asr.l   #1,d0
            move.l  #1664525,d1
            mulu.l  d1,d6
            addi.l  #1013904223,d6
            mac     a3,d6,acc0
            movclr  acc0,d1
            asr.l   #1,d1
            add.l   d1,d0
            move.l  d3,acc0
            sub.l   d3,d0
            mac     d7,d0,acc0
            movclr  acc0,d3
            move.l  #{k['K_BIAS8']},acc0
            mac     a5,d3,acc0
            mac     a5,d3,acc0
            movclr  acc0,d0
            addi.l  #0x80000000,d0
            move.l  d0,d1
            moveq   #24,d2
            lsr.l   d2,d1
            lea     TANH,a0
            lea     0(a0,d1.l*4),a0
            lsl.l   #8,d0
            lsr.l   #1,d0
            move.l  (a0)+,d1
            move.l  (a0),d2
            sub.l   d1,d2
            move.l  d1,acc0
            mac     d0,d2,acc0
            movclr  acc0,d0
            asr.l   #1,d0
            subi.l  #{MT.C['TB'] >> 1},d0
            move.l  {T['MK']}(a4),d1
            mac     d1,d0,acc0
            movclr  acc0,d0
            move.l  d0,d1
            sub.l   d4,d1
            move.l  d1,acc0
            move.l  d0,d4
            move.l  #{k['K_DCR']},d1
            mac     d1,d5,acc0
            movclr  acc0,d5
            move.l  #0x7fffffff,d1
            mac     d1,d5,acc0
            mac     d1,d5,acc0
            movclr  acc0,d0
            move.l  d0,(a1)+
            cmpa.l  a6,a1
            bne     mo
            move.l  d3,{T['LP']}(a4)
            move.l  d4,{T['DCX']}(a4)
            move.l  d5,{T['DCY']}(a4)
            move.l  d6,{T['RNG']}(a4)
            rts
'''


def data_text(tabs):
    out = ['    ; ================= Daten']
    for nm, b in tabs.items():
        out.append(f'    {nm}:')
        for i in range(0, len(b), 16):
            ws = struct.unpack('>%dI' % (len(b[i:i + 16]) // 4), b[i:i + 16])
            out.append('            dc.l    ' + ','.join(f'{w:#x}' for w in ws))
    return '\n'.join(out) + '\n'


def tables():
    t = dict(MT.tables())
    t['P12'] = struct.pack('>13I', *SM.p12_values())
    return t


def build(SS=None):
    """-> (Bytes der Nutzlast ab ORG, Labels, Texte). SS: Symbole von strings."""
    if SS is None:
        _, S7, _ = SM.build(); c, d, SS, _ = ST.build(S7)
    k = dict(KW, ST_RAT=SS['RAT2'], ST_ROF=SS['ROF2'], ST_MIMG=SS['MIMG2'], RBUILD=core.sym()['RBUILD'])
    text = code_text(k) + data_text(tables())
    E.LOG[:] = [x for x in E.LOG if not ORG <= x[0] < ORG + ROOM]
    a = A(ORG); asm(a, text, collections.defaultdict(int)); lab = dict(a.lab); n_code = len(a.b)
    blob = bytearray()
    def at(): return ORG + n_code + len(blob)
    while (n_code + len(blob)) % 4: blob += b'\0'
    lab['ROWS9'] = at(); rows = bytearray(9 * 32)
    struct.pack_into('>I', rows, 6 * 32, SM.D_DEC)
    struct.pack_into('>8I', rows, 7 * 32, ST.CH_DEC, 0, *range(ST.DBASE, ST.DBASE + 4), 0, 0)
    struct.pack_into('>8I', rows, 8 * 32, TONE_DEC, 0, *range(DBASE, DBASE + 4), 0, 0)
    blob += rows
    lab['VEC9'] = at(); blob += struct.pack('>9I', *range(1, 10))
    for nm in ('NAMES9', 'UPD9', 'RND9'):
        lab[nm] = at(); blob += bytes(36)
    lab['MAP9'] = at(); blob += bytes(range(9)) + bytes(3)
    lab['R10'] = at(); blob += bytes(80)
    lab['WNAMES'] = at(); blob += bytes(4 * len(MT.WAVES))
    w, h, pic = C.icon(ICON_FILE); assert (w, h) == (34, 34), (w, h)
    lab['MBM'] = at(); blob += C.bitmap(w, h, at() + 28, SM.ICON_MASK)
    lab['MICON'] = at(); blob += pic
    strs = {}
    for s in (NAME,) + MT.WAVES + tuple(x[0] for x in KNOBS) + tuple(x[1] for x in KNOBS):
        if s not in strs:
            strs[s] = at(); blob += s.encode() + b'\0'
    while len(blob) % 4: blob += b'\0'
    struct.pack_into('>%dI' % len(MT.WAVES), blob, lab['WNAMES'] - ORG - n_code, *[strs[w] for w in MT.WAVES])
    E.LOG[:] = [x for x in E.LOG if not ORG <= x[0] < ORG + ROOM]
    a = A(ORG); asm(a, text, dict(lab)); code = adone(a, lab)
    assert len(code) == n_code
    lab.update(a.lab)
    return code, bytes(blob), lab, strs


def tweak(img):
    base = apply(img, core.tweak(img))
    base = apply(base, SM.tweak(img))
    base = apply(base, ST.tweak(img))
    _, S7, s7 = SM.build()
    c8, d8, SS, s8 = ST.build(S7)
    code, data, lab, strs = build(SS)
    blob = bytearray(code + data)
    def put32(sym, vals):
        struct.pack_into('>%dI' % len(vals), blob, lab[sym] - ORG, *vals)
    put32('NAMES9', list(SM.NAMES_ORIG) + [s7[SM.MNAME], s8[ST.NAME], strs[NAME]])
    put32('UPD9', list(SM.UPD_ORIG) + [S7['SUPD'], SS['SUPD8'], lab['MUPD']])
    put32('RND9', list(SM.RND_ORIG) + [S7['SRND'], SS['SRND8'], lab['MRND']])
    assert len(blob) <= ROOM, (len(blob), ROOM)
    W = Writes(base)
    W.put(C.IMG_END + OFF, bytes(blob))
    smb = {va: new for va, _, new in SM.BOUNDS}
    for va in B8:
        old = smb[va] + 1
        W.hook(va, struct.pack('>H', old), struct.pack('>H', old + 1))
    W.hook(STEP_AT, ck_step(), bytes.fromhex('5c84'))                  # addq.l #6,d4: 9 Positionen ab x = 73
    W.hook(MAP_REF, struct.pack('>I', MAP_OLD), struct.pack('>I', lab['MAP9']))
    W.hook(SM.ALG_MAX, struct.pack('>I', (MACH - 1) << 8), struct.pack('>I', MACH << 8))
    for va in SM.ROW_REFS:
        W.hook(va, struct.pack('>I', SS['ROWS8']), struct.pack('>I', lab['ROWS9']))
    W.hook(SM.NAMES_REF, struct.pack('>I', SS['NAMES8']), struct.pack('>I', lab['NAMES9']))
    W.hook(SM.UPD_REF, struct.pack('>I', SS['UPD8']), struct.pack('>I', lab['UPD9']))
    W.hook(SM.RND_REF, struct.pack('>I', SS['RND8']), struct.pack('>I', lab['RND9']))
    W.hook(SM.RAT_HOOK, jmp(SS['RAT2']), jmp(lab['RAT3']))
    W.hook(SM.ROF_HOOK, jmp(SS['ROF2']), jmp(lab['ROF3']))
    W.hook(SM.KV_HOOK, jsr(SS['KV2']) + bytes.fromhex('4e71'), jsr(lab['KV3']) + bytes.fromhex('4e71'))
    W.hook(SM.IMG_HOOK, jmp(SS['MIMG2']), jmp(lab['MIMG3']))
    for i, (lng, sht, fld, slot, top, dflt, key, donor) in enumerate(KNOBS):
        W.put(C.PIMG(C.DTD(DBASE + i)), DT.desc_row(fld, slot, top, dflt, key, strs[lng], SM.SNARE_GROUP, strs[sht]))
        W.put(C.PIMG(C.DONOR + DBASE + i - C.NDESC0), bytes([donor]))
        W.put(C.PIMG(C.MACHMAP + DBASE + i - C.NDESC0), bytes([MACH if fld == 6 else 0xFF]))   # Glide / Noise: allgemein (wie Attack)
    l0, ln = C.LKX_SLOT['mono']
    for i, (knob, d) in enumerate(FKNOBS):
        W.put(C.PIMG(C.LKXT + 4 * (l0 + i)), struct.pack('>BBH', MACH, knob, d))
    # smp23: Glide / Noise (k 24 / 27) speichert jetzt der Core (Sound-Slot 3, Satz +80 / +81); MH bleibt ungenutzt im Code
    hooks = list(B8) + [STEP_AT, MAP_REF, SM.ALG_MAX] + list(SM.ROW_REFS) + [SM.NAMES_REF, SM.UPD_REF, SM.RND_REF, SM.RAT_HOOK,
                                                                           SM.ROF_HOOK, SM.KV_HOOK, SM.IMG_HOOK]
    return patch('mono', 18, 'Monom (monophonic synth machine)',
                 ["9th machine 'Monom': monophonic synth in the spirit of SH-101 / Minimoog / Pro-One / MS-20, warm and imperfect (own code).",
                  "COLOR = wave (SAW SQR PWM S+P TRI SYNC DTN RING), SHAPE = timbre of the wave, SWEEP = sub oscillator, CONTOUR = drive;"
                  " FUNC + PITCH = glide, FUNC + CONTOUR = noise.",
                  "Analog character: oscillator drift, random detune per note, free-running phases, soft asymmetric saturation, noise floor.",
                  f"Code and tables ({len(blob)} B) in the core's payload slot at {ORG:#x}; state per track at {RAM:#x}. Needs sampler and strings.",
                  "Erzeugt von v2/g2_mono.py."], W,
                 requires=['core', 'sampler', 'strings'], hooks=[f"{x:#x}" for x in hooks],
                 memory=[{"va": f"{ORG:#x}", "size": len(blob), "ram": True, "use": "payload slot 'mono' (code, tables)"},
                         {"va": f"{RAM:#x}", "size": 6 * TSTR, "ram": True, "use": "state per track"}],
                 symbols={kk: f"{lab[kk]:#x}" for kk in ('RAT3', 'ROF3', 'REC10', 'R10', 'KV3', 'MIMG3', 'WFMT', 'MH', 'MSTATE', 'MUPD',
                                                         'MUPD2', 'MUPD3', 'MRND', 'INC', 'SETINC', 'SINQ', 'OSC', 'TRI', 'SYNC', 'RING',
                                                         'MOUT', 'MBM', 'MICON', 'ROWS9', 'VEC9', 'NAMES9', 'UPD9', 'RND9', 'MAP9', 'WNAMES', 'SINT',
                                                         'TANH', 'GLT', 'SAWLP', 'DRVT', 'P12')},
                 params={"machine": MACH, "ram": f"{RAM:#x}", "tstride": TSTR, "state": T, "osc": OS})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    code, data, lab, _ = build()
    print(len(code), len(data), len(code) + len(data), ROOM)
