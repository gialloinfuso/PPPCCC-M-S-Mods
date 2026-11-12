#!/usr/bin/env python3
"""Mod 'strings' (v2, Patch 17, smp14; bis smp15 Nummer 20): 8. Maschine 'Strng', eine String-Ensemble-Maschine im Stil eines Solina
(Vorbild: string-machine von jpcima nach dem Modell von Peter Whiting, BSL-1.0; kein Code uebernommen, eigener Code).
Braucht den Core (Nutzlast) und den Sampler (7. Maschine, die Grenzen 5 -> 6 kommen von ihm; hier 6 -> 7).

Klang (je Spur, 48 kHz, Bloecke zu 32 Samples):
  Akkord wie die CHORD-Maschine: SHAPE = Akkordtyp, dieselbe Liste und dieselben Namen (die Rapporte liest die Maschine zur
  Laufzeit aus der Tabelle der Firmware 0x4012142c, nur ueber die Adresse). SHAPE 0 = ein Ton (Mono), 1 / 2 = zwei / vier
  leicht verstimmte Toene (Unisono). Je Ton zwei Saegezaehne 8' und 4' (phasenstarr wie beim Teiler, polyBLEP), frei
  laufend (kein Phasen-Reset beim Trig).
  COLOR = Lagen-Mischung 8' / 4' (0 nur 8', 64 beide, 127 nur 4'), SWEEP = Helligkeit (Hochpass 110 Hz, dann
  TPT-Tiefpass 800 Hz .. 9.7 kHz), CONTOUR = Ensemble (0 aus .. 127 voll: 3 Abgriffe, LFOs 0.62 / 5.9 Hz, 120 Grad versetzt,
  mono je Spur), DECAY = Amp-Decay der Firmware, FUNC + DECAY = Attack des Cores, PITCH / FINE wie ueblich.
  Strum (smp23, pro Spur im Sound): FUNC + SHAPE = Abstand (k 24: 0 = zusammen, 1..110 ms, 111..127 Notenwerte wie Patch 04 im
  Tempo, smp36), FUNC + COLOR = Pattern (k 27: UP, DOWN, RND, 1324, 1423, 4132, 4231; fehlende Toene uebersprungen). Die Deskriptoren
  (88 / 89) setzt der Mod 'strum'; ohne ihn sind k 24 / 27 auf Vlvt nicht bedienbar. Jeder Ton mit eigener Einblendung
  (8 Bloecke); die Huellkurve der Spur teilen sie.
Maschine (Bestandsliste nach Modded-Cycles notes/18 und 19, MIT; eigener Code):
  Grenzen 6 -> 7 (Parameter-Suche 0x4005a6a6, Maschine setzen 0x400147a4, Rad 0x400148aa / b2, MACHINES-Bild 0x400a25e0,
  Stimmen-Schleife 0x400a7dba / f4), 8 Positionen ab x = 73 (0x400a26e8, 0x400a26a2), Byte 0x40118647 = 7, Algorithm-Max 7.
  Tabellen mit 8 Eintraegen in der Nutzlast: Namen, update / render, Zeilen (8 x 32 B, Zeile 7 = Decay 75, COLOR..CONTOUR
  71..74) + Vektor [1..8].
  Deskriptoren: die der CHORD-Maschine (71..74, 75) - keine neuen, also auch Bereiche, Defaults, Formatierer (Akkordnamen)
  und Kurznamen von CHORD. Die Anwendbarkeit 0x4000aa9a (Maschine des Deskriptors == Maschine der Spur) gilt fuer die
  Strng-Spur auch mit 5 (Haken APP 0x4000aad0); die langen Namen beim Drehen (0x4000b22a, einziger Aufrufer das Popup der
  Parameter) heissen auf einer Strng-Spur 'Octave Mix', 'Chord', 'Tone', 'Ensemble' (LNM).
  Maschinen-Saetze: 8 -> der von CHORD (RAT2 vor dem des Samplers), Maschine 7 -> CHORD (ROF2); Knopf-Vektor [1..8] (KV2);
  MACHINES-Bilder: die von CHORD (MIMG2). Kleine Icons der Firmware zeigen fuer 6 / 7 schon CHORD.
Speicher: Nutzlast-Platz 'strings' (Code, Tabellen), Zustand je Spur 0x43180000 + 0x1200 t (+0x200 Ring 1024 x 4 B).
Aufruf: g2_strings.py [out.json]
"""
import collections, math, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import g2_sampler as SM
import cfemac as E
import g2_dtab as DT
from cfasm import asm, done as adone

MACH = 7
OFF, ROOM = C.PAY_SLOT['strings']
ORG = C.PAY + OFF
# ---- Firmware 1.13
CHORD_REC = SM.REC_BASE + 6 * 76     # Maschinen-Satz von CHORD (Index 6 = Maschine 5)
CH_DESC, CH_DEC = (71, 72, 73, 74), 75
CH_TAB = 0x4012142C                  # Rapporte der Akkorde (4 x Q26 je SHAPE 0..37)
NCHORD = 38
DBASE, DN = C.DESC_SLOT['strings']    # smp18: eigene Deskriptoren (Tabelle des Cores), Feld 6, Maschine 7 (MACHMAP)
# (langer Name, kurzer Name, Slot, Maximum, Default, Sortierschluessel, Spender-Objekt): Spender = Anzeige von CHORD (SHAPE: Akkordnamen)
KNOBS = (('Octave Mix', 'OCTV', 11, 0x7F00, 0x2800, 40, 71), ('Chord', 'CHRD', 12, 0x2500, 0x0300, 50, 72),
         ('Tone', 'TONE', 13, 0x7F00, 0x3C00, 60, 73), ('Ensemble', 'ENSM', 14, 0x7F00, 0x4000, 70, 74))
MARK_X, MARK_CK = 0x400A26A2, (2, 'ebea3e9376d4482e85c067de72a3ccb700c7956f7e0bbc118f19c22b0c02ba1a')     # moveq #80,d4
MAP7, MAP_CK = 0x40118647, (1, '6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d')
# Grenzen, die der Sampler auf 6 gesetzt hat -> 7 (die Positionen 7 -> 8); 0x4005a340 / 0x4005a572 bleiben (Deskriptor-Feld)
B7 = (0x4005A6A6, 0x400147A4, 0x400148AA, 0x400148B2, 0x400A25E0, 0x400A7DBA, 0x400A7DF4, 0x400A26E8)
VOICE0, VSTRIDE = SM.VOICE0, SM.VSTRIDE
# ---- Zustand je Spur (RAM ausserhalb des Images)
RAM, TSTR, RING, NRING = 0x43180000, 0x1200, 0x200, 1024
MAGIC = 0x53545231                   # 'STR1' in der Stimme +0x70 (die Firmware loescht die Stimme beim Maschinenwechsel)
T = dict(BLK=0x00, NN=0x04, HPLP=0x08, IC1=0x0C, IC2=0x10, FA1=0x14, FA2=0x18, FA3=0x1C, W=0x20, PH1=0x24, PH2=0x28,
         DC0=0x2C, DC1=0x30, DC2=0x34, DI0=0x38, DI1=0x3C, DI2=0x40, DT0=0x44, DT1=0x48, DT2=0x4C, WG=0x50, DRY=0x54,
         ENS=0x58, PERM=0x5C, OSC=0x60, ENV=0x160, STG=0x170)   # PERM: Rang je Ton (4 B), beim Trig aus dem Strum-Pattern;
# smp24: ENV Huellkurve je Ton (4 x 4 B, 0..2^31), STG Stufe je Ton (0 Attack, 2 Decay)
O = dict(P=0, INC=4, KINV=8, PREV=12, PEND=16, G=20, DG=24, TG=28)   # Oszillator (32 B), 8 Stueck: 2 j = 8', 2 j + 1 = 4'
NOSC = 8
# ---- Klang
FS = 48000
INC0 = 2 ** 32 * 440 * 2 ** (-69 / 12) / FS          # Note 0 (C-1)
INCMAX = int(2 ** 32 * 6000 / FS)                      # 8' hoechstens 6 kHz (4' = doppelt)
NLO, NHI = 12, 108
GN = {1: 0.34, 2: 0.15, 4: 0.07}                       # je Ton (n Toene): 2 n Oszillatoren x GN <= 0.96, der Block laeuft nie ueber
HPF = 110.0
FC0, FOCT, QSVF = 800.0, 3.6, 0.75
D0, A1, A2 = 0.0065, 0.0016, 0.00022                   # Ensemble: Grundverzoegerung, Tiefe langsam / schnell (s)
F1, F2 = 0.62, 5.9                                     # LFO-Frequenzen (Hz)
WCOMP = 1.6                                            # Nass-Ausgleich: 3 schwebende Abgriffe gemittelt sind leiser als trocken
UNI = {0: (0.0,), 1: (-7.0, 7.0), 2: (-10.0, -3.5, 3.5, 10.0)}   # Unisono: Verstimmung in Cent
ICON_FILE = C.ROOT / 'v2' / 'art' / 'vlvt_klein.bmp'
NAMES_L = tuple(x[0] for x in KNOBS)
NAME = 'Vlvt'                        # Name im MACHINES-Menue (Pip 03.11.: 'Vlvt', vorher 'Strng')
SIZE_PAY = ROOM


def q31(x):
    v = int(round(x * 2 ** 31)); v = max(-2 ** 31, min(2 ** 31 - 1, v))
    return v & 0xFFFFFFFF


def gains(c):
    c = c / 127
    return min(1.0, 2 * (1 - c)), min(1.0, 2 * c)


def ens(c):
    """CONTOUR 0..127 -> (Nass, Tiefe-Faktor)"""
    c = c / 127
    return 0.85 * min(1.0, 2 * c), 0.4 + 0.6 * c


def svf_coef(s):
    fc = FC0 * 2 ** (FOCT * s / 127)
    g = math.tan(math.pi * fc / FS); k = 1 / QSVF
    a1 = 1 / (1 + g * (g + k)); a2 = g * a1; a3 = g * a2
    return a1, a2, a3


def tables():
    """Eigene Tabellen (keine Firmware-Daten)."""
    d = {}
    d['P12'] = struct.pack('>13I', *SM.p12_values())
    d['SINT'] = struct.pack('>257I', *[q31(0.999 * math.sin(2 * math.pi * i / 256)) for i in range(257)])
    d['COLT'] = b''.join(struct.pack('>II', q31(gains(c)[0]), q31(gains(c)[1])) for c in range(128))
    d['SVFT'] = b''.join(struct.pack('>III', *[q31(x) for x in svf_coef(s)]) for s in range(128))
    et = b''
    for c in range(128):
        wet, m = ens(c)
        et += struct.pack('>IIII', q31(wet * 2 / 3 * WCOMP), q31(1 - wet), int(round(m * A1 * FS * 2 ** 22)), int(round(m * A2 * FS * 2 ** 22)))
    d['ENST'] = et
    u = b''
    for s in range(3):
        cs = UNI[s] + (0.0,) * (4 - len(UNI[s]))
        u += struct.pack('>4I', *[int(round(2 ** 26 * 2 ** (x / 1200))) for x in cs])
    d['UNIT'] = u
    d['GNT'] = struct.pack('>5I', 0, q31(GN[1]), q31(GN[2]), 0, q31(GN[4]))
    d['SRTAB'] = C.strum_rtab()                                          # smp23: Strum-Raenge je Pattern, Notenwerte, Zufall (RAM)
    d['SNUN'] = b''.join(struct.pack('>H', C.strum_units(p)) for p in C.STRUM_NOTEP) + b'\0\0'   # smp36
    d['SRNG'] = struct.pack('>I', 0x6B8B4567)
    return d


KW = dict(VOICE0=VOICE0, VSTRIDE=VSTRIDE, RAM=RAM, TSTR=TSTR, RING=RING, NRING=NRING, MAGIC=MAGIC, DECLUT=SM.DECLUT,
          AMPENV=SM.AMPENV, VCA=SM.VCA, TEMPO=C.TEMPO, KC=C.STRUM_KC, NMS=C.STRUM_NMS, FADE_MIN=C.STRUM_FADE_MIN, OWN=core.sym()['OWN'], NPAT=len(C.STRUM_PATS), PRND=C.STRUM_RND, CH_TAB=CH_TAB, INC0=int(round(INC0)),
          INCMAX=INCMAX, NLO=NLO << 16, NHI=NHI << 16, HPK=q31(1 - math.exp(-2 * math.pi * HPF / FS)),
          D0Q=int(round(D0 * FS * 2 ** 22)), DPH1=int(round(F1 * 32 / FS * 2 ** 32)), DPH2=int(round(F2 * 32 / FS * 2 ** 32)),
          ACT_TRACK=SM.ACT_TRACK, KITP=SM.KITP, NOSC=NOSC, NCH=NCHORD - 1,
          **{f'T_{k}': v for k, v in T.items()}, **{f'O_{k}': v for k, v in O.items()})


def code_text(S):
    k = dict(KW, **{x: S[x] for x in ('SM_RAT', 'SM_ROF', 'ICON_A', 'ICON_B', 'SPRITE', 'IMG_RET', 'SM_MIMG', 'RBUILD', 'SM_DCK')})
    mimg2 = SM.mimg_text('MIMG2', MACH, 5, 'VBM', k['SM_MIMG'])
    return f'''
    ; ================= Maschine: Saetze, Knopf-Vektor, MACHINES-Bild (smp18: eigene Deskriptoren 76..79 in der Tabelle des Cores)
    ; 0x4004df5c (Satz n = Maschine + 1): 8 -> eigener Satz (aus dem von CHORD, 71..74 -> 76..79), sonst der Sampler
    RAT2:   move.l  4(sp),d0
            moveq   #8,d1
            cmp.l   d1,d0
            bne     ra1
            jmp     REC9
    ra1:    jmp     {k['SM_RAT']}
    ; 0x4004df76 (Satz der Maschine m): 7 -> eigener Satz
    ROF2:   move.l  4(sp),d0
            moveq   #7,d1
            cmp.l   d1,d0
            bne     ro1
            jmp     REC9
    ro1:    jmp     {k['SM_ROF']}
    REC9:   pea     {DBASE}.w
            pea     {CH_DESC[0]}.w
            pea     6.w
            pea     R9
            jsr     {k['RBUILD']}
            lea     16(sp),sp
            rts
    ; 0x4001e8da (jsr statt 'move.l 32(sp),d0 ; movea.l 104(a2),a1'): Maschine 6 / 7 -> Vektor [1..8]
    KV2:    move.l  36(sp),d0
            movea.l 104(a2),a1
            moveq   #6,d1
            cmp.l   d1,d0
            blt     kv1
            lea     VEC8,a1
    kv1:    rts
    ; MACHINES-Bild: Vlvt -> grosses Bild von CHORD, eigenes kleines Icon (Pip); sonst der Sampler (Grit) bzw. die Firmware
{mimg2}
    ; ================= update[7] (pmod, Stimme, Parameter)
    SUPD8:  lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 52(sp),a2
            movea.l 56(sp),a3
            mvs.b   36(a3),d0                ; Amp-Decay wie TONE, kein Gate
            lea     {k['DECLUT']},a0
            move.l  0(a0,d0.l*4),d1
            move.l  d1,0x250(a2)
            clr.l   0x24c(a2)
            jsr     STATE                    ; a4 = Zustand der Spur (erster Gebrauch: leer)
            tst.l   0x38(a2)                 ; Trig: Strum-Zaehler von vorn, Reihenfolge aus dem Pattern
            beq     u1
            clr.l   {k['T_BLK']}(a4)
            clr.l   {k['T_STG']}(a4)
            jsr     SPERM
            bra     u2
    u1:     move.l  {k['T_BLK']}(a4),d0
            cmpi.l  #0xffff,d0
            bcc     u2
            addq.l  #1,d0
            move.l  d0,{k['T_BLK']}(a4)
    u2:     move.l  48(sp),d6                ; pmod (Note << 16)
            jsr     PITCH                    ; d7 = Schritt des Grundtons
            jsr     CHORD                    ; Toene: Schritte, Verstaerkungen (Oszillatoren TG / DG / INC / KINV)
            jsr     FILT
            jsr     ENSU
            move.l  #0x80000000,d0           ; smp24: Huellkurve der Spur flach (Decay je Ton in RAMP), Attack des Cores aus
            move.l  d0,0x250(a2)
            move.l  a2,d0
            subi.l  #{k['VOICE0']},d0
            move.l  #{k['VSTRIDE']},d1
            divu.l  d1,d0
            lea     {k['OWN']},a0
            moveq   #1,d1
            move.b  d1,0(a0,d0.l)
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts

    ; a2 = Stimme -> a4 = Zustand; neu (Magie fehlt): Zustand + Ring leer, Phasen versetzt, Verzoegerungen = D0
    STATE:  move.l  a2,d0
            subi.l  #{k['VOICE0']},d0
            move.l  #{k['VSTRIDE']},d1
            divu.l  d1,d0
            move.l  #{k['TSTR']},d1
            mulu.l  d1,d0
            addi.l  #{k['RAM']},d0
            movea.l d0,a4
            move.l  0x70(a2),d0
            cmpi.l  #{k['MAGIC']},d0
            bne     st1
            rts
    st1:    movea.l a4,a0
            move.l  #{TSTR // 4 - 1},d0
    st2:    clr.l   (a0)+
            subq.l  #1,d0
            bpl     st2
            lea     {k['T_OSC']}(a4),a0
            moveq   #0,d0
            moveq   #0,d1
    st3:    move.l  d0,d2                    ; Phase p (8': j * 0x5d000000, 4': 2 p), gespeichert als Saege q = p ^ 0x80000000
            eori.l  #0x80000000,d2
            move.l  d2,(a0)
            move.l  d0,d2
            add.l   d2,d2
            eori.l  #0x80000000,d2
            move.l  d2,32(a0)
            addi.l  #0x5D000000,d0
            lea     64(a0),a0
            addq.l  #1,d1
            moveq   #4,d2
            cmp.l   d2,d1
            bne     st3
            move.l  #{k['D0Q']},d0
            move.l  d0,{k['T_DC0']}(a4)
            move.l  d0,{k['T_DC1']}(a4)
            move.l  d0,{k['T_DC2']}(a4)
            move.l  #0xffff,d0
            move.l  d0,{k['T_BLK']}(a4)
            move.l  #{k['MAGIC']},d0
            move.l  d0,0x70(a2)
            rts

    ; d6 = pmod, a3 = Parameter -> d7 = Schritt (0.32) des Grundtons (Note 12..108)
    PITCH:  mvs.w   20(a3),d0                ; PITCH
            subi.l  #0x4000,d0
            lsl.l   #8,d0
            mvs.w   34(a3),d1                ; FINE
            subi.l  #0x4000,d1
            lsl.l   #3,d1
            add.l   d1,d0
            add.l   d6,d0                    ; Note << 16
            cmpi.l  #{k['NLO']},d0
            bge     pi1
            move.l  #{k['NLO']},d0
    pi1:    cmpi.l  #{k['NHI']},d0
            ble     pi2
            move.l  #{k['NHI']},d0
    pi2:    move.l  #{12 << 16},d1
            move.l  d0,d2
            remu.l  d1,d3:d2                 ; d3 = im Ton (16.16)
            divu.l  d1,d2                    ; Oktave
            move.l  d3,d4
            swap    d4
            andi.l  #0xffff,d4               ; Halbton
            andi.l  #0xffff,d3               ; Bruchteil
            lea     P12,a0
            move.l  0(a0,d4.l*4),d5
            move.l  4(a0,d4.l*4),d0
            sub.l   d5,d0
            mulu.l  d3,d0
            swap    d0
            andi.l  #0xffff,d0
            add.l   d0,d5                    ; 2^(Ton / 12), 16.16
            move.l  #{k['INC0']},d4
            lsl.l   d2,d4                    ; Schritt der Note 12 * Oktave
            jsr     MUL16
            move.l  d4,d7
            rts
    ; d4 = d4 * d5 (16.16) >> 16 ; zerstoert d1 / d2
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

    ; Akkord: d7 = Schritt des Grundtons, a3 = Parameter, a4 = Zustand. Fuer Ton j (0..3): 8' = Oszillator 2 j, 4' = 2 j + 1:
    ; INC, KINV, TG (Ziel-Verstaerkung) und DG = (TG - G) / 32. Toene ueber n: TG = 0 (blenden in einem Block aus).
    CHORD:  lea     -40(sp),sp               ; 0..15 Rapporte (Q16), 16 n, 20 Abstand (1/8 Bloecke), 24 frei, 28 g8 * gn, 32 g4 * gn
            mvz.b   24(a3),d0                ; SHAPE
            moveq   #{k['NCH']},d1
            cmp.l   d1,d0
            bls     ch1
            move.l  d1,d0
    ch1:    moveq   #2,d1
            cmp.l   d1,d0
            bhi     ch2
            lea     UNIT,a0                  ; Unisono 1 / 2 / 4
            lsl.l   #4,d0
            adda.l  d0,a0
            lsr.l   #4,d0
            moveq   #1,d1
            lsl.l   d0,d1                    ; n = 1, 2, 4
            bra     ch3
    ch2:    lea     {k['CH_TAB']},a0          ; Akkord der Firmware (Q26)
            lsl.l   #4,d0
            adda.l  d0,a0
            moveq   #4,d1
    ch3:    move.l  d1,16(sp)
            move.l  d1,{k['T_NN']}(a4)
            moveq   #10,d2
            moveq   #0,d0
    ch4:    move.l  0(a0,d0.l*4),d3
            lsr.l   d2,d3                    ; Q26 -> Q16
            move.l  d3,0(sp,d0.l*4)
            addq.l  #1,d0
            moveq   #4,d3
            cmp.l   d3,d0
            bne     ch4
            ; Verstaerkungen: COLOR -> g8 / g4, mal gn(n)
            mvz.b   22(a3),d0
            lsl.l   #3,d0
            lea     COLT,a0
            adda.l  d0,a0
            move.l  (a0)+,d2                 ; g8
            move.l  (a0),d3                  ; g4
            lea     GNT,a0
            move.l  16(sp),d0
            move.l  0(a0,d0.l*4),d4          ; gn
            movclr  acc0,d0
            mac     d2,d4,acc0
            movclr  acc0,d2
            mac     d3,d4,acc0
            movclr  acc0,d3
            move.l  d2,28(sp)
            move.l  d3,32(sp)
            ; Strum (smp23): Abstand = k 24 (FUNC + SHAPE) in 1/8 Bloecken
            mvz.b   {2 * C.K_STIME}(a3),d0
            jsr     SSTEP
            move.l  d0,20(sp)
            ; Toene
            lea     {k['T_OSC']}(a4),a5
            moveq   #0,d6                    ; j
    cj:     cmp.l   16(sp),d6
            blt     cj1
            clr.l   {k['O_TG']}(a5)          ; Ton nicht im Akkord: ausblenden
            clr.l   {32 + k['O_TG']}(a5)
            moveq   #0,d0                    ; smp24: seine Huellkurve von vorn
            lea     {k['T_ENV']}(a4),a0
            move.l  d0,0(a0,d6.l*4)
            lea     {k['T_STG']}(a4),a0
            move.b  d0,0(a0,d6.l)
            jmp     cjx
    cj1:    move.l  d7,d4
            move.l  0(sp,d6.l*4),d5
            jsr     MUL16                    ; Schritt des Tons
            cmpi.l  #{k['INCMAX']},d4
            bls     cj2
            move.l  #{k['INCMAX']},d4
    cj2:    move.l  d4,{k['O_INC']}(a5)
            move.l  d4,d0
            clr.w   d0
            swap    d0
            moveq   #-1,d1
            divu.l  d0,d1
            move.l  d1,{k['O_KINV']}(a5)
            add.l   d4,d4                    ; 4'
            move.l  d4,{32 + k['O_INC']}(a5)
            move.l  d4,d0
            clr.w   d0
            swap    d0
            moveq   #-1,d1
            divu.l  d0,d1
            move.l  d1,{32 + k['O_KINV']}(a5)
            jsr     RAMP                     ; d0 = Einblendung des Tons (Q31)
            move.l  28(sp),d1
            movclr  acc0,d2
            mac     d1,d0,acc0
            movclr  acc0,d2
            move.l  d2,{k['O_TG']}(a5)
            move.l  32(sp),d1
            mac     d1,d0,acc0
            movclr  acc0,d2
            move.l  d2,{32 + k['O_TG']}(a5)
    cjx:    move.l  {k['O_TG']}(a5),d0       ; DG = (TG - G) / 32 (beide Lagen)
            sub.l   {k['O_G']}(a5),d0
            asr.l   #5,d0
            move.l  d0,{k['O_DG']}(a5)
            move.l  {32 + k['O_TG']}(a5),d0
            sub.l   {32 + k['O_G']}(a5),d0
            asr.l   #5,d0
            move.l  d0,{32 + k['O_DG']}(a5)
            lea     64(a5),a5
            addq.l  #1,d6
            moveq   #4,d0
            cmp.l   d0,d6
            bne     cj
            lea     40(sp),sp
            rts
    ; smp24: Huellkurve von Ton d6 (Stapel des Aufrufers +4: 20 n, 24 Abstand in 1/8 Bloecken) -> d0 (Q31). Rang = Zahl der Toene
    ; i < n mit PERM[i] < PERM[j] (fehlende uebersprungen), Einsatz = (Rang x Abstand) >> 3 Bloecke. Ab dem Einsatz: Attack
    ; (k 23; 0 = sofort, spaetere Einsaetze 1/4, 1/2, voll), dann Decay mit dem Faktor der Firmware (DECLUT, Stimme +0x250).
    ; Vlvt hat kein GATE (wie bisher). Zerstoert d0-d4, a0 (d5 / d7 / a5 bleiben)
    RAMP:   lea     {k['T_PERM']}(a4),a0
            mvz.b   0(a0,d6.l),d3            ; PERM[j]
            moveq   #0,d0                    ; Rang
            move.l  20(sp),d2                ; i = n .. 1
    rpl:    subq.l  #1,d2
            bmi     rp1
            mvz.b   0(a0,d2.l),d4
            cmp.l   d3,d4
            bcc     rpl
            addq.l  #1,d0
            bra     rpl
    rp1:    mulu.l  24(sp),d0
            lsr.l   #3,d0
            move.l  d0,d2                    ; Einsatz
            move.l  {k['T_BLK']}(a4),d1
            sub.l   d0,d1                    ; Bloecke seit dem Einsatz
            bmi     rpz
            lea     {k['T_STG']}(a4),a0
            tst.b   0(a0,d6.l)
            beq     rpa
            lea     {k['T_ENV']}(a4),a0      ; Decay
            move.l  0(a0,d6.l*4),d0
            jsr     VEMUL
            move.l  d0,0(a0,d6.l*4)
            bra     rpq
    rpz:    moveq   #0,d0                    ; vor dem Einsatz: Stufe 0; smp39: Pegel blendet aus (* 3/4 je Block) statt 0
            lea     {k['T_STG']}(a4),a0
            move.b  d0,0(a0,d6.l)
            lea     {k['T_ENV']}(a4),a0
            move.l  0(a0,d6.l*4),d0
            move.l  d0,d1
            lsr.l   #2,d1
            sub.l   d1,d0
            cmpi.l  #{k['FADE_MIN']:#x},d0
            bcc     rpz1
            moveq   #0,d0
    rpz1:   move.l  d0,0(a0,d6.l*4)
            bra     rpq
    rpa:    jmp     VATK
    ; d0 (0..2^31) -> Q31 (voll = 0x7fffffff)
    rpq:    tst.l   d0
            bpl     rpq9
            move.l  #0x7fffffff,d0
    rpq9:   rts
    ; Attack-Stufe (d1 Bloecke seit dem Einsatz, d2 Einsatz)
    VATK:   lea     {k['T_ENV']}(a4),a0
            mvz.b   {2 * C.K_EXT0}(a3),d0
            bne     va1
            tst.l   d2
            beq     vfl
            tst.l   d1
            bne     va2
            move.l  #0x20000000,d0
            bra     vst
    va2:    subq.l  #1,d1
            bne     vfl
            move.l  #0x40000000,d0
            bra     vst
    va1:    mulu.l  d0,d0                    ; Zuwachs je Block = 2^31 * 32 / (96000 (a / 127)^2) wie der Attack des Cores
            move.l  #96000,d1
            mulu.l  d1,d0
            move.l  #16129,d1
            divu.l  d1,d0
            moveq   #32,d1
            cmp.l   d1,d0
            bcs     vfl
            move.l  #0x80000000,d1
            divu.l  d0,d1
            lsl.l   #5,d1
            move.l  d1,d0
            add.l   0(a0,d6.l*4),d0
            bcs     vfl
            bpl     vst
    vfl:    move.l  #0x80000000,d0
            move.l  d0,0(a0,d6.l*4)
            lea     {k['T_STG']}(a4),a0
            moveq   #2,d0
            move.b  d0,0(a0,d6.l)
            move.l  #0x7fffffff,d0
            rts
    vst:    move.l  d0,0(a0,d6.l*4)
            rts
    ; d0 = E * f / 2^31, f = -(Faktor an Stimme +0x250). Zerstoert d1-d4
    VEMUL:  move.l  0x250(a2),d1
            neg.l   d1
            move.l  d0,d2
            clr.w   d2
            swap    d2                       ; Eh
            andi.l  #0xffff,d0               ; El
            move.l  d1,d3
            clr.w   d3
            swap    d3                       ; fh
            andi.l  #0xffff,d1               ; fl
            mulu.l  d2,d1
            mulu.l  d3,d0
            add.l   d1,d0
            lsr.l   #8,d0
            lsr.l   #7,d0
            mulu.l  d3,d2
            add.l   d2,d2
            add.l   d2,d0
            rts
    ; Strum-Abstand: d0 = Wert 0..127 -> d0 = 1/8 Bloecke (0 = zusammen; smp36: ms, dann Notenwerte wie C.strum_step8)
    SSTEP:  tst.l   d0
            beq     ss9
            moveq   #{k['NMS']},d1
            cmp.l   d1,d0
            bhi     ss1
            move.l  #3000,d1
            mulu.l  d1,d0
            moveq   #{k['NMS']},d1
            divu.l  d1,d0
            rts
    ss1:    cmpi.l  #127,d0
            bls     ss2
            moveq   #127,d0
    ss2:    subi.l  #{k['NMS'] + 1},d0
            lea     SNUN,a0
            mvz.w   0(a0,d0.l*2),d0
            move.l  #{k['KC']},d1
            mulu.l  d1,d0
            move.l  {k['TEMPO']},d1
            beq     ssz
            divu.l  d1,d0
    ss9:    rts
    ssz:    moveq   #0,d0
            rts
    ; Trig: Strum-Pattern k 27 (FUNC + COLOR) -> Rang je Ton in PERM (RND: Fisher-Yates mit eigenem Zufall). Zerstoert d0-d3, a0, a1
    SPERM:  mvz.b   {2 * C.K_SPAT}(a3),d0
            moveq   #{k['NPAT'] - 1},d1
            cmp.l   d1,d0
            bls     sq1
            moveq   #0,d0
    sq1:    lea     {k['T_PERM']}(a4),a1
            moveq   #{k['PRND']},d1
            cmp.l   d1,d0
            beq     sqr
            lea     SRTAB,a0
            move.l  0(a0,d0.l*4),d0
            move.l  d0,(a1)
            rts
    sqr:    move.l  #0x00010203,d0
            move.l  d0,(a1)
            moveq   #3,d3                    ; j = 3..1
    sq2:    move.l  SRNG,d0
            move.l  #1664525,d1
            muls.l  d1,d0
            addi.l  #1013904223,d0
            move.l  d0,SRNG
            clr.w   d0
            swap    d0
            move.l  d3,d1
            addq.l  #1,d1
            mulu.l  d1,d0
            clr.w   d0
            swap    d0                       ; r = 0..j
            mvz.b   0(a1,d3.l),d1
            mvz.b   0(a1,d0.l),d2
            move.b  d2,0(a1,d3.l)
            move.b  d1,0(a1,d0.l)
            subq.l  #1,d3
            bne     sq2
            rts

    ; SWEEP -> Koeffizienten des Tiefpasses
    FILT:   mvz.b   26(a3),d0
            moveq   #12,d1
            mulu.l  d1,d0
            lea     SVFT,a0
            adda.l  d0,a0
            move.l  (a0)+,d0
            move.l  d0,{k['T_FA1']}(a4)
            move.l  (a0)+,d0
            move.l  d0,{k['T_FA2']}(a4)
            move.l  (a0)+,d0
            move.l  d0,{k['T_FA3']}(a4)
            rts

    ; CONTOUR -> Ensemble: Nass / Trocken, LFOs, Ziel-Verzoegerungen am Blockende und Schritte je Sample (10.22)
    ENSU:   mvz.b   28(a3),d0
            lsl.l   #4,d0
            lea     ENST,a0
            adda.l  d0,a0
            move.l  (a0)+,d0
            move.l  d0,{k['T_WG']}(a4)
            move.l  (a0)+,d1
            move.l  d1,{k['T_DRY']}(a4)
            movea.l (a0)+,a5                 ; Tiefe langsam
            movea.l (a0)+,a6                 ; Tiefe schnell
            move.l  {k['T_ENS']}(a4),d2
            move.l  d0,{k['T_ENS']}(a4)
            or.l    d0,d2
            bne     en1
            rts                              ; aus und war aus
    en1:    move.l  {k['T_PH1']}(a4),d6
            addi.l  #{k['DPH1']},d6
            move.l  d6,{k['T_PH1']}(a4)
            move.l  {k['T_PH2']}(a4),d7
            addi.l  #{k['DPH2']},d7
            move.l  d7,{k['T_PH2']}(a4)
            lea     {k['T_DC0']}(a4),a3      ; a3: DCi, +12 DIi, +24 DTi
            moveq   #3,d5
    en2:    move.l  d6,d0
            jsr     SINQ
            move.l  d0,d3
            move.l  d7,d0
            jsr     SINQ
            move.l  #{k['D0Q']},d1
            move.l  d1,acc1
            mac     a5,d3,acc1
            mac     a6,d0,acc1
            movclr  acc1,d1                  ; Ziel
            move.l  d1,24(a3)
            sub.l   (a3),d1
            asr.l   #5,d1
            move.l  d1,12(a3)
            addq.l  #4,a3
            addi.l  #0x55555555,d6
            addi.l  #0x55555555,d7
            subq.l  #1,d5
            bne     en2
            rts
    ; d0 = Phase (0.32) -> d0 = sin (Q31), Tabelle 256 + 1 linear; zerstoert d1 / d2 / a0, acc3 leer
    SINQ:   move.l  d0,d1
            moveq   #24,d2
            lsr.l   d2,d1                    ; Index
            lea     SINT,a0
            lea     0(a0,d1.l*4),a0
            lsl.l   #8,d0
            lsr.l   #1,d0                    ; Bruchteil Q31
            move.l  (a0)+,d1
            move.l  (a0),d2
            sub.l   d1,d2
            move.l  d1,acc3
            mac     d0,d2,acc3
            movclr  acc3,d0
            rts

    ; ================= render[7] (Ausgang, Stimme): Oszillatoren -> Hochpass + Tiefpass -> Ensemble -> Amp / VCA der Firmware
    SRND8:  lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 48(sp),a1
            movea.l 52(sp),a2
            jsr     STATE
            lea     128(a1),a6
    rz:     clr.l   (a1)+
            cmpa.l  a6,a1
            bne     rz
            lea     {k['T_OSC']}(a4),a5
            moveq   #{NOSC},d0
            move.l  d0,-(sp)
    ro:     jsr     OSC
            lea     32(a5),a5
            subq.l  #1,(sp)
            bne     ro
            addq.l  #4,sp
            jsr     LPF
            tst.l   {k['T_ENS']}(a4)
            beq     rn
            jsr     ENS
            bra     rq9
    rn:     jsr     OUT4
    rq9:    move.l  a2,-(sp)
            jsr     {k['AMPENV']}
            move.l  a2,(sp)
            move.l  52(sp),-(sp)
            jsr     {k['VCA']}
            addq.l  #8,sp
            movea.l 48(sp),a0                ; smp41: Uebergang beim neuen Akkord glaetten (DCK des Samplers)
            jsr     {k['SM_DCK']}
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts

    ; Oszillator a5 auf den Block a6 - 128 .. a6 addieren. Phase als Saege q = p ^ 0x80000000 (Umbruch = Ueberlauf V),
    ; polyBLEP mit 1 Sample Verzoegerung: Ausgang n = q(n - 1) - u^2 beim Umbruch in n, das Sample danach + (1 - u)^2
    ; (u = Phase nach dem Umbruch / Schritt); |Ausgang| <= 1, also Block + g * Ausgang ohne Saettigung (GN).
    OSC:    movea.l {k['O_G']}(a5),a0
            movea.l {k['O_DG']}(a5),a3
            move.l  a0,d0
            bne     oc1
            move.l  a3,d0
            bne     oc1
            move.l  {k['O_INC']}(a5),d0      ; still: nur die Phase weiter, Zustand des Saegezahns neu
            lsl.l   #5,d0
            add.l   {k['O_P']}(a5),d0
            move.l  d0,{k['O_P']}(a5)
            move.l  d0,{k['O_PREV']}(a5)
            clr.l   {k['O_PEND']}(a5)
            rts
    oc1:    movem.l (a5),d3-d7               ; q, INC, KINV, PREV, PEND
            lea     -128(a6),a1
            tst.l   d7
            beq     ol
            add.l   d4,d3                    ; Umbruch im letzten Sample des Blocks davor: + (1 - u)^2
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
    ow:     move.l  d3,d1                    ; Umbruch: u (16 Bit) = (p >> 16) * KINV >> 16
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
            lsr.l   #1,d2                    ; (1 - u)^2 (Q31)
            mulu.l  d1,d1
            lsr.l   #1,d1                    ; u^2
            neg.l   d1
            add.l   d6,d1
            mac     a0,d1,acc0
            move.l  d3,d6
            movclr  acc0,d0
            add.l   d0,(a1)+
            adda.l  a3,a0
            cmpa.l  a6,a1
            bne     ow2
            move.l  d2,d7                    ; Umbruch im letzten Sample: das naechste bekommt (1 - u)^2
            bra     oe
    ow2:    add.l   d4,d3                    ; Sample nach dem Umbruch (kein zweiter Umbruch: Schritt < 2^31)
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
            move.l  {k['O_TG']}(a5),d0
            move.l  d0,{k['O_G']}(a5)
            rts

    ; Hochpass (1 Pol, vor dem Nachfuehren) + TPT-Tiefpass, halbe Skala, auf der Stelle
    LPF:    lea     -128(a6),a1
            move.l  {k['T_HPLP']}(a4),d6
            move.l  #{k['HPK']},d7
            move.l  {k['T_IC1']}(a4),d4
            move.l  {k['T_IC2']}(a4),d5
            movea.l {k['T_FA1']}(a4),a0
            movea.l {k['T_FA2']}(a4),a3
            movea.l {k['T_FA3']}(a4),a5
    fl:     move.l  (a1),d0
            asr.l   #1,d0
            move.l  d0,d1
            sub.l   d6,d1                    ; Hochpass
            move.l  d6,acc0
            mac     d7,d1,acc0
            movclr  acc0,d6
            move.l  d1,d2
            sub.l   d5,d2                    ; v3
            mac     a0,d4,acc0
            mac     a3,d2,acc0
            movclr  acc0,d3                  ; v1
            move.l  d5,acc1
            mac     a3,d4,acc1
            mac     a5,d2,acc1
            movclr  acc1,d0                  ; v2 = Tiefpass
            add.l   d3,d3
            sub.l   d4,d3
            move.l  d3,d4
            move.l  d0,d1
            add.l   d1,d1
            sub.l   d5,d1
            move.l  d1,d5
            move.l  d0,(a1)+
            cmpa.l  a6,a1
            bne     fl
            move.l  d6,{k['T_HPLP']}(a4)
            move.l  d4,{k['T_IC1']}(a4)
            move.l  d5,{k['T_IC2']}(a4)
            rts
    ; ohne Ensemble: Ausgang = 4 x halbe Skala (gesaettigt)
    OUT4:   lea     -128(a6),a1
            move.l  #0x7fffffff,d1
    o4:     move.l  (a1),d0
            mac     d1,d0,acc0
            mac     d1,d0,acc0
            mac     d1,d0,acc0
            mac     d1,d0,acc0
            movclr  acc0,d0
            move.l  d0,(a1)+
            cmpa.l  a6,a1
            bne     o4
            rts
    ; Ensemble: Ring (Viertel-Skala) schreiben, 3 Abgriffe linear (Verzoegerungen 10.22 in a2 / a3 / a4, Schritte auf dem
    ; Stapel), Ausgang = 4 x (Trocken x + Nass * 2/3 * Summe), gesaettigt
    ENS:    move.l  a2,-(sp)
            move.l  a4,-(sp)
            lea     -12(sp),sp
            move.l  {k['T_DI0']}(a4),(sp)
            move.l  {k['T_DI1']}(a4),4(sp)
            move.l  {k['T_DI2']}(a4),8(sp)
            lea     -128(a6),a1
            lea     {k['RING']}(a4),a0
            move.l  {k['T_W']}(a4),d7
            move.l  {k['T_WG']}(a4),d5
            movea.l {k['T_DRY']}(a4),a5
            movea.l {k['T_DC0']}(a4),a2
            movea.l {k['T_DC1']}(a4),a3
            movea.l {k['T_DC2']}(a4),a4
            moveq   #22,d3
    el:     move.l  (a1),d0
            mac     a5,d0,acc2
            mac     a5,d0,acc2
            mac     a5,d0,acc2
            mac     a5,d0,acc2
            asr.l   #1,d0
            move.l  d7,d2
            lsr.l   d3,d2
            move.l  d0,0(a0,d2.l*4)          ; Ring[w] = x / 2
            moveq   #0,d1
            move.l  d7,d2                    ; Abgriff 0
            sub.l   a2,d2
            move.l  d2,d6
            lsr.l   d3,d6
            lsl.l   #8,d2
            lsl.l   #2,d2
            lsr.l   #1,d2
            move.l  0(a0,d6.l*4),d0
            add.l   d0,d1
            addq.l  #1,d6
            andi.l  #{NRING - 1},d6
            move.l  0(a0,d6.l*4),d6
            sub.l   d0,d6
            mac     d2,d6,acc1
            move.l  d7,d2                    ; Abgriff 1
            sub.l   a3,d2
            move.l  d2,d6
            lsr.l   d3,d6
            lsl.l   #8,d2
            lsl.l   #2,d2
            lsr.l   #1,d2
            move.l  0(a0,d6.l*4),d0
            add.l   d0,d1
            addq.l  #1,d6
            andi.l  #{NRING - 1},d6
            move.l  0(a0,d6.l*4),d6
            sub.l   d0,d6
            mac     d2,d6,acc1
            move.l  d7,d2                    ; Abgriff 2
            sub.l   a4,d2
            move.l  d2,d6
            lsr.l   d3,d6
            lsl.l   #8,d2
            lsl.l   #2,d2
            lsr.l   #1,d2
            move.l  0(a0,d6.l*4),d0
            add.l   d0,d1
            addq.l  #1,d6
            andi.l  #{NRING - 1},d6
            move.l  0(a0,d6.l*4),d6
            sub.l   d0,d6
            mac     d2,d6,acc1
            movclr  acc1,d0
            add.l   d0,d1                    ; Summe der Abgriffe
            mac     d5,d1,acc2
            mac     d5,d1,acc2
            mac     d5,d1,acc2
            mac     d5,d1,acc2
            movclr  acc2,d0
            move.l  d0,(a1)+
            addi.l  #{1 << 22},d7
            adda.l  (sp),a2
            adda.l  4(sp),a3
            adda.l  8(sp),a4
            cmpa.l  a6,a1
            bne     el
            lea     12(sp),sp
            movea.l (sp)+,a4
            movea.l (sp)+,a2
            move.l  d7,{k['T_W']}(a4)
            move.l  {k['T_DT0']}(a4),{k['T_DC0']}(a4)
            move.l  {k['T_DT1']}(a4),{k['T_DC1']}(a4)
            move.l  {k['T_DT2']}(a4),{k['T_DC2']}(a4)
            rts
'''


def data_text(tabs):
    """Datenteil (nach dem Code): Tabellen als dc.l, Texte als Bytes"""
    out = ['    ; ================= Daten']
    def words(name, b):
        out.append(f'    {name}:')
        for i in range(0, len(b), 16):
            ws = struct.unpack('>%dI' % (len(b[i:i + 16]) // 4), b[i:i + 16])
            out.append('            dc.l    ' + ','.join(f'{w:#x}' for w in ws))
    for nm, b in tabs.items():
        words(nm, b)
    return '\n'.join(out) + '\n'


def build(S=None):
    """-> (Bytes der Nutzlast ab ORG, Labels). S: Symbole des Samplers (RAT, ROF, MIMG ...)."""
    if S is None:
        _, S, _ = SM.build()
    tabs = tables()
    kw = {'SM_DCK': S['DCK'], 'SM_RAT': S['RAT'], 'SM_ROF': S['ROF'], 'SM_MIMG': S['MIMG'], 'RBUILD': core.sym()['RBUILD'], 'ICON_A': SM.ICON_A, 'ICON_B': SM.ICON_B, 'SPRITE': SM.SPRITE,
          'IMG_RET': SM.IMG_RET}
    text = code_text(kw) + data_text(tabs)
    E.LOG[:] = [x for x in E.LOG if not ORG <= x[0] < ORG + ROOM]
    a = A(ORG)
    asm(a, text, collections.defaultdict(int)); lab = dict(a.lab)
    n_code = len(a.b)
    # Datenteil hinter dem Code: Zeilen, Vektor, Namen, update / render, lange Namen, Texte
    blob = bytearray()
    def at(): return ORG + n_code + len(blob)
    while (n_code + len(blob)) % 4: blob += b'\0'
    lab['ROWS8'] = at()
    rows = bytearray(8 * 32)
    struct.pack_into('>I', rows, 6 * 32, SM.D_DEC)                     # Zeile des Samplers wie bei ihm
    struct.pack_into('>8I', rows, 7 * 32, CH_DEC, 0, *range(DBASE, DBASE + 4), 0, 0)   # Vlvt: Decay von CHORD, eigene 76..79 (die setzt auch der Konstruktor)
    blob += rows
    lab['VEC8'] = at(); blob += struct.pack('>8I', *range(1, 9))
    lab['NAMES8'] = at(); blob += bytes(32)
    lab['UPD8'] = at(); blob += bytes(32)
    lab['RND8'] = at(); blob += bytes(32)
    lab['R9'] = at(); blob += bytes(80)                                  # eigener Maschinen-Satz (RAM, beim ersten Gebrauch)
    w, h, pic = C.icon(ICON_FILE); assert (w, h) == (34, 34), (w, h)     # eigenes kleines Icon (Pip)
    lab['VBM'] = at(); blob += C.bitmap(w, h, at() + 28, SM.ICON_MASK)
    lab['VICON'] = at(); blob += pic
    strs = {}
    for s in (NAME,) + NAMES_L + tuple(x[1] for x in KNOBS):
        strs[s] = at(); blob += s.encode() + b'\0'
    while len(blob) % 4: blob += b'\0'
    lab.update({f'S_{i}': strs[s] for i, s in enumerate((NAME,) + NAMES_L)})
    # zweiter Durchgang mit allen Adressen
    E.LOG[:] = [x for x in E.LOG if not ORG <= x[0] < ORG + ROOM]
    a = A(ORG); asm(a, text, dict(lab)); code = adone(a, lab)
    assert len(code) == n_code, (len(code), n_code)
    lab.update(a.lab)
    return code, bytes(blob), lab, strs


def tweak(img):
    base = apply(img, core.tweak(img))
    base = apply(base, SM.tweak(img))
    parts, S, sstr = SM.build()
    code, data, lab, strs = build(S)
    n_code = len(code)
    blob = bytearray(code + data)
    def put32(sym, vals):
        o = lab[sym] - ORG
        struct.pack_into('>%dI' % len(vals), blob, o, *vals)
    put32('NAMES8', list(SM.NAMES_ORIG) + [sstr[SM.MNAME], strs[NAME]])
    put32('UPD8', list(SM.UPD_ORIG) + [S['SUPD'], lab['SUPD8']])
    put32('RND8', list(SM.RND_ORIG) + [S['SRND'], lab['SRND8']])
    assert len(blob) <= ROOM, (len(blob), ROOM)
    W = Writes(base)
    assert len(base) == C.IMG_END - BASE + C.PAYSZ
    W.put(C.IMG_END + OFF, bytes(blob))
    # Grenzen 6 -> 7 (vom Sampler), Positionen 7 -> 8 ab x = 73, Byte 7 der Maschinen-Tabelle, Algorithm-Max 7
    smb = {va: new for va, _, new in SM.BOUNDS}
    for va in B7:
        old = smb[va]
        W.hook(va, struct.pack('>H', old), struct.pack('>H', old + 1))
    W.hook(MARK_X, MARK_CK, struct.pack('>H', 0x7849))
    W.hook(MAP7, MAP_CK, bytes([MACH]))
    W.hook(SM.ALG_MAX, struct.pack('>I', (MACH - 1) << 8), struct.pack('>I', MACH << 8))
    # Tabellen mit 8 Eintraegen (statt der 7 des Samplers)
    for va in SM.ROW_REFS:
        W.hook(va, struct.pack('>I', S['ROWS7']), struct.pack('>I', lab['ROWS8']))
    W.hook(SM.NAMES_REF, struct.pack('>I', S['NAMES7']), struct.pack('>I', lab['NAMES8']))
    W.hook(SM.UPD_REF, struct.pack('>I', S['UPD7']), struct.pack('>I', lab['UPD8']))
    W.hook(SM.RND_REF, struct.pack('>I', S['RND7']), struct.pack('>I', lab['RND8']))
    # Umleitungen vor die des Samplers
    W.hook(SM.RAT_HOOK, jmp(S['RAT']), jmp(lab['RAT2']))
    W.hook(SM.ROF_HOOK, jmp(S['ROF']), jmp(lab['ROF2']))
    W.hook(SM.KV_HOOK, jsr(S['KV']) + bytes.fromhex('4e71'), jsr(lab['KV2']) + bytes.fromhex('4e71'))
    W.hook(SM.IMG_HOOK, jmp(S['MIMG']), jmp(lab['MIMG2']))
    # smp18: eigene Deskriptoren 76..79 in der Tabelle des Cores (Feld 6, Maschine 7, Anzeige von CHORD)
    for i, (lng, sht, slot, top, dflt, key, donor) in enumerate(KNOBS):
        W.put(C.PIMG(C.DTD(DBASE + i)), DT.desc_row(6, slot, top, dflt, key, strs[lng], SM.SNARE_GROUP, strs[sht]))
        W.put(C.PIMG(C.DONOR + DBASE + i - C.NDESC0), bytes([donor]))
        W.put(C.PIMG(C.MACHMAP + DBASE + i - C.NDESC0), bytes([MACH]))
    hooks = list(B7) + [MARK_X, MAP7, SM.ALG_MAX] + list(SM.ROW_REFS) + [SM.NAMES_REF, SM.UPD_REF, SM.RND_REF, SM.RAT_HOOK,
                                                                        SM.ROF_HOOK, SM.KV_HOOK, SM.IMG_HOOK]
    return patch('strings', 17, 'Vlvt (string machine)',
                 ["8th machine 'Vlvt': string ensemble in the style of a Solina (idea: string-machine by jpcima after Peter"
                  " Whiting, BSL-1.0; own code). Needs the sampler (7th machine).",
                  "SHAPE = chord (same list and names as CHORD; 0 = mono, 1 / 2 = unison 2 / 4), COLOR = 8'/4' mix,"
                  " SWEEP = tone (low-pass), CONTOUR = ensemble (3 modulated taps per track), DECAY / FUNC + DECAY = amp decay / attack.",
                  "Strum per track (FUNC + SHAPE = time, FUNC + COLOR = pattern, needs the strum mod) staggers the chord notes; each note has its own attack (FUNC + DECAY) / decay (DECAY) envelope.",
                  f"Code and tables ({len(blob)} B) live in the core's payload slot at {ORG:#x}; state per track at {RAM:#x}.",
                  "Erzeugt von v2/g2_strings.py."], W,
                 requires=['core', 'sampler'], hooks=[f"{x:#x}" for x in hooks],
                 memory=[{"va": f"{ORG:#x}", "size": len(blob), "ram": True, "use": "payload slot 'strings' (code, tables)"},
                         {"va": f"{RAM:#x}", "size": 6 * TSTR, "ram": True, "use": "state + ensemble ring per track"}],
                 symbols={kk: f"{lab[kk]:#x}" for kk in ('RAT2', 'ROF2', 'KV2', 'MIMG2', 'VBM', 'VICON', 'REC9', 'R9', 'SUPD8', 'SRND8', 'STATE',
                                                         'PITCH', 'CHORD', 'RAMP', 'VATK', 'VEMUL', 'SSTEP', 'SPERM', 'FILT', 'ENSU', 'SINQ', 'OSC', 'LPF', 'OUT4', 'ENS',
                                                         'ROWS8', 'VEC8', 'NAMES8', 'UPD8', 'RND8', 'P12', 'SINT', 'COLT',
                                                         'SVFT', 'ENST', 'UNIT', 'GNT')},
                 params={"machine": MACH, "ram": f"{RAM:#x}", "tstride": TSTR, "state": {kk: v for kk, v in T.items()},
                         "osc": {kk: v for kk, v in O.items()}})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    code, data, lab, _ = build()
    print(len(code), len(data), len(code) + len(data), ROOM)
