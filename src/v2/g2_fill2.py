#!/usr/bin/env python3
"""Mod 'fill2' (v2): zweiter FILL. Unabhaengig (braucht keinen Core).
Bedienung (Pip 26.10.2026): PAGE halten wie fuer FILL, dazu FUNC halten -> Fill 2 statt Fill 1.
  Auch mit eingerastetem Fill (TRACK + PAGE): FUNC halten -> Fill 2.
Neue Trig-Bedingungen 'FIL2' (spielt nur in Fill 2) und '!FIL2' (spielt nur ausserhalb von Fill 2), im Chance-Menue direkt
  nach FILL / !FILL. Waehrend Fill 2 gelten FILL wie 'kein Fill' (FILL still, !FILL spielt).
Gespeichert als 64 / 65 (Stock-Werte 0..63 bleiben, Patterns kompatibel). Die UI sieht 'Positionen': Getter 0x40015fd0 und
  Setter 0x40016010 rechnen um (POS: 0,1 -> 0,1 ; 64,65 -> 2,3 ; 2..63 -> 4..65), Anzeigen arbeiten mit Positionen.
  Nur der Sequencer (0x40054952/6e) und Kopien Step zu Step (0x40017540, roh) lesen das Byte direkt.
Keine Firmware-Tabellen kopiert: die Namen kommen weiter aus den Tabellen der Firmware, NMAP / BMAP rechnen nur den Index um;
  FIL2 / !FIL2 stehen in zwei eigenen Zeigern. Verschobene Originalbefehle (Getter, Setter) kommen aus dem Image (A.orig).
Firmware 1.13:
  Bedingungsbyte pro Step: Track-Daten +0x204, Setter 0x40016010 begrenzt auf 63 (0x40016052/58) -> 65.
  Deskriptor 19 'Trig Cond' Max 16128 (63<<8) -> 16640 (65<<8).
  Getter: 0x40015ff6..0x40016009 -> jmp GM (liest, POS, zurueck nach 0x4001600a). Setter: Speichern 0x4001605a -> jsr SM.
  Text 0x4004a4ce: Grenze 63 (0x4004a4d0) -> 65; lea Namentabelle + Index (0x4004a4f6, 10 B) -> jsr NMAP.
  Anzeige 0x40050046: Grenze (0x400500a6) -> 65; lea Grundnamen (0x400500a8) -> jsr BMAP (a0 so, dass a0 + 4*Index auf den
    richtigen Eintrag zeigt); Negationszeichen 1,3,5,7 -> ungerade bis 9 (0x4005010c), Prozent-Bereich 8..28 -> 10..30 (0x400500da).
  Auswertung 0x400913f0 (Track a0, Step, Bedingung d0, a1): Haken 0x40091416 -> EV. d0 != 0 = nicht spielen.
    Fill an = 0x40fde818 (PAGE / TRACK + PAGE). FUNC gehalten = Tastenbitmap 0x40f95744 (Index aus 0x4010ae5c[1]).
smp21 (Pip 04.11.): Reihenfolge und neue Bedingungen (gespeichert bleibt alles, Stock-Werte 0..63 unveraendert):
  Liste = '---' | 1:2 .. 8:8, 1:12 .. 12:12, 1:16 .. 16:16 | FILL !FILL FIL2 !FIL2 PTC !PTC PRE !PRE NEI !NEI 1st !1st LST !LST
  | 1% .. 99%. Neu gespeichert: 66 PTC / 67 !PTC, 68 LST / 69 !LST, 70..81 x:12, 82..97 x:16 (NCOND 98).
  PTC: ein neu gewaehltes Pattern wartet (Kette 0x40a7863c neu gesetzt: Position 0x40a78634 < 0) und ist ein anderes als das
    laufende (0x40a7887c). Ketten-Durchlauf zaehlt nicht. Direct Jump wechselt am naechsten Step (bis dahin gilt PTC).
  LST: am Ende dieses Durchlaufs kommt ein anderes Pattern (naechster Ketten-Eintrag wie 0x400555ae rechnet), auch in Ketten.
  x:12 / x:16: wie A:B der Firmware (Durchlauf-Zaehler 0x40fde81c je Spur, Rest der Division).
  Umrechnung ueber Tabellen POS2ST / ST2POS, Anzeige ueber FLAGS (Negationsstrich, Prozent); Namen der Firmware ueber Adressen.
Speicher: Masken 0x40189930 (EV, F2, GM, SM), 0x4018a220 (XEV, PTC, LST, S2P, P2S, NMAP, BMAP, PRC, NEGF), 0x4018cd48
  (Tabellen), 0x40184df8 (eigene Namenszeiger), 0x40185308 (Texte). Kein RAM.
Aufruf: g2_fill2.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C

M_C, M_X, M_T, M_N, M_S = 0x40189930, 0x4018A220, 0x4018CD48, 0x40184DF8, 0x40185308
SIZE = {M_C: 376, M_X: 376, M_T: 376, M_N: 272, M_S: 272}
C_FIL2, C_NFIL2, C_PTC, C_NPTC, C_LST, C_NLST = 64, 65, 66, 67, 68, 69
R12, R16 = 70, 82                                                    # x:12 ab 70, x:16 ab 82
NCOND = R16 + 16                                                     # 98
CHAIN0, CPOS, CLEN, CURPAT = 0x40A7863C, 0x40A78634, 0x40A78638, 0x40A7887C
# eigene Namen fuer 64..97 (Name, Grundname fuer die grosse Anzeige)
OWN = ([('FIL2', 'FIL2'), ('!FIL2', 'FIL2'), ('PTC', 'PTC'), ('!PTC', 'PTC'), ('LST', 'LST'), ('!LST', 'LST')]
       + [(f'{a}:12', f'{a}:12') for a in range(1, 13)] + [(f'{a}:16', f'{a}:16') for a in range(1, 17)])
ORDER = (list(range(29, 64)) + list(range(R12, R12 + 12)) + list(range(R16, R16 + 16))
         + [0, 1, C_FIL2, C_NFIL2, C_PTC, C_NPTC, 2, 3, 4, 5, 6, 7, C_LST, C_NLST] + list(range(8, 29)))   # Position -> gespeichert
assert sorted(ORDER) == list(range(NCOND))
NEGS = {1, 3, 5, 7, C_NFIL2, C_NPTC, C_NLST}                         # Negationsstrich in der grossen Anzeige
PRCS = set(range(8, 29))
# Firmware (Pruefwerte: Laenge + SHA-256 der Originalbytes)
EV_HOOK, EV_ORIG = 0x40091416, (8, '6fe6e4cae4a95f0acb550b57ba8d5e92d0af0bb2df080807c9f5d3f8596f0cec')
EV_CONT, EV_DEF, EV_EXIT = 0x4009141E, 0x40091622, 0x4009161A
FILL_NOW = 0x40FDE818
KEYMAP, KEYIDX = 0x40F95744, 0x4010AE5C
SET_CL1, SET_CL2 = 0x40016052, 0x40016058                            # moveq #63,d0 / moveq #63,d1
DESC_MAX = C.DESC(19) + 12
TXT_LIM, TXT_LEA = 0x4004A4D0, 0x4004A4F6                            # moveq #63,d2 / lea Namen,a0 ; lea (a0,d0.l*4),a0
NAMES0, BASEN0 = 0x401090B4, 0x40108F54                              # Namentabelle / Grundnamen der Firmware (64 Zeiger)
DSP_LIM, DSP_LEA = 0x400500A6, 0x400500A8                            # moveq #63,d1 / lea Grundnamen,a0
NEG_LIM = 0x4005010C                                                 # moveq #7,d0 (Negationszeichen bis Index 7)
PRC_AT = 0x400500DA                                                  # d0 = idx - 8 ; d1 = 20  ->  d0 = idx - 10
GET_HOOK, GET_RET = 0x40015FF6, 0x4001600A
GET_ORIG = (20, '21133b4c794606fd02f1ea76b21327367e84c9421bf2d172580920cb578bbdac')
SET_HOOK, SET_ORIG = 0x4001605A, (10, '8e3ddf90085607adb96ccffd99ddd15cd98f0123c174da669ce708dfda266cc7')
SMALL = [  # (VA, Pruefwert, neue Bytes)
    (SET_CL1, (2, 'f4fe429b77392bd272678ba7d265d4f6ecc18c97d38aaf8bd0eacc250312ed28'), "70%02x" % (NCOND - 1)),   # moveq #97,d0
    (SET_CL2, (2, '8500e6e3760f30ec85f007695ffcd97decb7a7f3219fe576e66e7fa4e877d73f'), "72%02x" % (NCOND - 1)),   # moveq #97,d1
    (TXT_LIM, (2, '14b4035526671323ac6a5c577b0aeaeaed54aa6c3596660e962437ef9d02a6e8'), "74%02x" % (NCOND - 1)),   # moveq #97,d2
    (DSP_LIM, (2, '8500e6e3760f30ec85f007695ffcd97decb7a7f3219fe576e66e7fa4e877d73f'), "72%02x" % (NCOND - 1)),   # moveq #97,d1
]
NEG_CK = (12, 'bb98af53e05b7ef6574c4b137f68398a9eb9eca3e808f40ec99bf3e2ba02a7ee')   # moveq #7 ; cmp ; bcs ; btst #0 ; beq
NEG_SKIP = 0x4005013C
PRC_CK = (6, 'd9f5e3327fa41ddac8ee2607170249dd15971239e235d5f5867efef67008febe')    # moveq #20,d1 ; move.l d2,d0 ; subq.l #8,d0
TXT_CK = (10, 'ba381dd36d95d2e6d21ecc3e46afb8a78135bc0b91945125fee3961349c14e32')
DSP_CK = (6, 'cd6ad9274dfa8679428daa40ef0257d2d97756bf1f2b0a0c60fbfdccececab1d')


def pos(sv):
    """gespeicherter Wert -> Position in der Liste"""
    return ORDER.index(sv) if 0 <= sv < NCOND else sv


def stored(p):
    return ORDER[p] if 0 <= p < NCOND else p


def func_bit(img):
    idx = struct.unpack('>i', img[KEYIDX + 4 * C.KEY_FUNC - BASE:KEYIDX + 4 * C.KEY_FUNC - BASE + 4])[0]
    assert 0 <= idx and 1 <= (idx & 7) <= 7, idx
    return KEYMAP + (idx >> 3), idx & 7


def tables():
    """M_T: POS2ST, ST2POS, FLAGS (Bit 0 Negationsstrich, Bit 1 Prozent) je NCOND Bytes; M_N: eigene Zeiger (Namen, Grundnamen)
    fuer 64..97; M_S: Texte. -> (Teile, Labels)"""
    st2pos = bytes(pos(v) for v in range(NCOND))
    flags = bytes((1 if v in NEGS else 0) | (2 if v in PRCS else 0) for v in ORDER)
    t = bytes(ORDER) + st2pos + flags
    lab = dict(POS2ST=M_T, ST2POS=M_T + NCOND, FLAGS=M_T + 2 * NCOND)
    sb, sa = bytearray(), {}
    for nm in sorted({x for pair in OWN for x in pair}):
        sa[nm] = M_S + len(sb); sb += nm.encode() + b'\0'
    nt = b''.join(struct.pack('>I', sa[n]) for n, _ in OWN) + b''.join(struct.pack('>I', sa[b]) for _, b in OWN)
    lab.update(OWNN=M_N, OWNB=M_N + 4 * len(OWN))
    return {M_T: t, M_N: nt, M_S: bytes(sb)}, lab, sa


def xcode(lab):
    """M_X (cfasm): neue Bedingungen, Umrechnung Position <-> gespeichert, Namen / Anzeige nach Position."""
    return f'''
    ; XEV: Bedingung d0 = 66..97 (von EV), d1 = Durchlauf-Zaehler, a0 Spur, a1: Ergebnis d0 (0 = spielt) -> EV_EXIT
    XEV:    cmpi.l  #{C_PTC},d0
            beq     xptc
            cmpi.l  #{C_NPTC},d0
            beq     xnptc
            cmpi.l  #{C_LST},d0
            beq     xlst
            cmpi.l  #{C_NLST},d0
            beq     xnlst
            cmpi.l  #{NCOND - 1},d0
            bhi     xdef
            cmpi.l  #{R16},d0
            bcc     x16
            subi.l  #{R12},d0
            moveq   #12,d3
            bra     xrm
    x16:    subi.l  #{R16},d0
            moveq   #16,d3
    xrm:    move.l  d1,d2                    ; Rest = Zaehler mod B (wie A:B der Firmware)
            divu.l  d3,d2
            muls.l  d3,d2
            neg.l   d2
            add.l   d1,d2
            cmp.l   d2,d0
            sne.b   d0
            andi.l  #1,d0
            jmp     {EV_EXIT}
    xptc:   jsr     PTC
            moveq   #1,d0
            eor.l   d2,d0
            jmp     {EV_EXIT}
    xnptc:  jsr     PTC
            move.l  d2,d0
            jmp     {EV_EXIT}
    xlst:   jsr     LST
            moveq   #1,d0
            eor.l   d2,d0
            jmp     {EV_EXIT}
    xnlst:  jsr     LST
            move.l  d2,d0
            jmp     {EV_EXIT}
    xdef:   jmp     {EV_DEF}
    ; PTC: d2 = 1, wenn eine neu gewaehlte Kette wartet (Position < 0) und ihr erstes Pattern nicht das laufende ist. d3.
    PTC:    moveq   #0,d2
            tst.l   {CPOS}
            bge     pt9
            move.l  {CHAIN0},d3
            cmp.l   {CURPAT},d3
            beq     pt9
            moveq   #1,d2
    pt9:    rts
    ; LST: d2 = 1, wenn am Ende dieses Durchlaufs ein anderes Pattern kommt (naechster Eintrag wie die Firmware). d3.
    LST:    move.l  {CPOS},d3
            blt     ls0
            addq.l  #1,d3
            bra     ls1
    ls0:    moveq   #0,d3
    ls1:    cmp.l   {CLEN},d3
            blt     ls2
            moveq   #0,d3
    ls2:    lsl.l   #3,d3
            move.l  a0,-(sp)
            lea     {CHAIN0},a0
            move.l  0(a0,d3.l),d3
            movea.l (sp)+,a0
            moveq   #0,d2
            cmp.l   {CURPAT},d3
            beq     ls9
            moveq   #1,d2
    ls9:    rts
    ; PRC: statt moveq #20,d1 ; move.l d2,d0 ; subq.l #8,d0 -> danach cmp.l d0,d1 ; scc = Prozent (FLAGS Bit 1)
    PRC:    moveq   #1,d0
            moveq   #0,d1
            cmpi.l  #{NCOND - 1},d2
            bhi     pr9
            move.l  a0,-(sp)
            lea     {lab['FLAGS']},a0
            mvz.b   0(a0,d2.l),d1            ; ColdFire: btst #imm nicht mit Index-Adresse (smp21-Absturz)
            movea.l (sp)+,a0
            btst    #1,d1
            beq     pr0
            moveq   #0,d0
            moveq   #1,d1
            rts
    pr0:    moveq   #0,d1
    pr9:    rts
    ; NEGF: d0 = 1, wenn Position d2 einen Negationsstrich bekommt (FLAGS Bit 0)
    NEGF:   moveq   #0,d0
            cmpi.l  #{NCOND - 1},d2
            bhi     ng9
            lea     {lab['FLAGS']},a0
            mvz.b   0(a0,d2.l),d0
            andi.l  #1,d0
    ng9:    rts
'''


def xcode2(lab):
    """hinter dem Code von M_C (cfasm): Umrechnung und Anzeige nach Position."""
    return f'''
    ; S2P: d0 gespeichert -> Position (ungueltig: bleibt). P2S: d1 Position -> gespeichert. Nur d0 / d1.
    S2P:    cmpi.l  #{NCOND - 1},d0
            bhi     s2p9
            move.l  a0,-(sp)
            lea     {lab['ST2POS']},a0
            mvz.b   0(a0,d0.l),d0
            movea.l (sp)+,a0
    s2p9:   rts
    P2S:    cmpi.l  #{NCOND - 1},d1
            bhi     p2s9
            move.l  a0,-(sp)
            lea     {lab['POS2ST']},a0
            mvz.b   0(a0,d1.l),d1
            movea.l (sp)+,a0
    p2s9:   rts
    ; NMAP: d0 = Position 0..97 -> a0 = Zeiger auf den Namens-Eintrag (Firmware-Tabelle oder eigene). d1 bleibt.
    NMAP:   lea     {lab['POS2ST']},a0
            mvz.b   0(a0,d0.l),d0
            cmpi.l  #64,d0
            bcc     nm1
            lsl.l   #2,d0
            lea     {NAMES0},a0
            adda.l  d0,a0
            rts
    nm1:    subi.l  #64,d0
            lsl.l   #2,d0
            lea     {lab['OWNN']},a0
            adda.l  d0,a0
            rts
    ; BMAP: d2 = Position -> a0 so, dass 0(a0,d2.l*4) der Grundname ist. d1, d2 bleiben.
    BMAP:   cmpi.l  #{NCOND - 1},d2
            bhi     bm8
            lea     {lab['POS2ST']},a0
            mvz.b   0(a0,d2.l),d0
            cmpi.l  #64,d0
            bcc     bm1
            lsl.l   #2,d0
            lea     {BASEN0},a0
            adda.l  d0,a0
            bra     bm2
    bm1:    subi.l  #64,d0
            lsl.l   #2,d0
            lea     {lab['OWNB']},a0
            adda.l  d0,a0
    bm2:    move.l  d2,d0
            lsl.l   #2,d0
            suba.l  d0,a0
            rts
    bm8:    lea     {BASEN0},a0
            rts
'''


def build(img):
    import collections
    from cfasm import asm, done as adone
    tp, tl, sa = tables()
    xl = collections.defaultdict(int, tl)
    for _ in range(2):
        ax = A(M_X); asm(ax, xcode(tl), xl)
        xl = dict(ax.lab, **tl)
    xb = adone(ax, xl)
    y0 = M_C + ((len(raw(img, collections.defaultdict(int))[0]) + 3) & ~3)
    yl = collections.defaultdict(int, tl)
    for _ in range(2):
        ay = A(y0); asm(ay, xcode2(tl), yl)
        yl = dict(ay.lab, **tl)
    yb = adone(ay, yl)
    xl.update(yl)
    code, rl = raw(img, xl)
    assert M_C + len(code) <= y0
    code = code + bytes(y0 - M_C - len(code)) + yb
    lab = dict(rl); lab.update({k: v for k, v in xl.items() if isinstance(k, str) and k.isupper()})
    lab.update({f'S_{k.replace("!", "N").replace(":", "_")}': v for k, v in sa.items()})
    parts = {M_C: code, M_X: xb}; parts.update(tp)
    return parts, lab


def raw(img, xl):
    """Code ab M_C (Haken-nahe Teile mit verschobenen Originalbefehlen). XEV / S2P / P2S aus xl (Code in M_X)."""
    from cfasm import asm, done as adone
    fb, fbit = func_bit(img)
    assert 1 <= fbit <= 7, fbit
    a = A(M_C)
    asm(a, f'''
    ; ================= EV: statt moveq #63,d2 ; cmp.l d0,d2 ; bcs.w default. d2/d3 frei (gesichert), d1/a0/a1 erhalten.
    EV:     moveq   #1,d2                    ; Bedingung > 1?
            cmp.l   d0,d2
            bcs     ef
            bsr     F2                       ; FILL / !FILL ohne Fill 2: Firmware
            beq     orig
            moveq   #1,d2                    ; Fill 2: FILL -> 1 (still), !FILL -> 0 (spielt)
            eor.l   d2,d0
            jmp     {EV_EXIT:#x}
    ef:     moveq   #{C_FIL2},d2
            cmp.l   d0,d2
            beq     f2
            moveq   #{C_NFIL2},d2
            cmp.l   d0,d2
            beq     nf2
            moveq   #{C_NFIL2},d2            ; smp21: 66..97 (und darueber) -> XEV
            cmp.l   d0,d2
            blt     xev
    orig:   orig    {EV_HOOK:#x},4           ; verschobene Originalbefehle (Grenze 63), dann wie die Firmware
            bcs     def
            jmp     {EV_CONT:#x}
    def:    jmp     {EV_DEF:#x}
    xev:    jmp     XEV
    f2:     bsr     F2                       ; FIL2: spielt nur in Fill 2
            moveq   #1,d0
            eor.l   d3,d0
            jmp     {EV_EXIT:#x}
    nf2:    bsr     F2                       ; !FIL2: still in Fill 2
            move.l  d3,d0
            jmp     {EV_EXIT:#x}
    ; ================= F2: d3 = 1, wenn Fill an und FUNC gehalten (Z = !d3). Benutzt d2.
    F2:     moveq   #0,d3
            tst.b   {FILL_NOW:#x}
            beq     fr
            move.b  {fb:#x},d3               ; Tastenbyte
            lsr.l   #{fbit},d3
            moveq   #1,d2
            and.l   d2,d3
    fr:     rts
    ; ================= GM: Getter ab 0x40015ff6 (a2 = Objekt, d2 = Step): Byte lesen, -> Position (S2P), weiter 0x4001600a
    GM:     orig    {GET_HOOK:#x},20         ; verschobene Originalbefehle: Daten holen, Byte lesen (aus dem Image)
            extb.l  d0
            jsr     S2P                      ; -1 und Ungueltiges bleiben
            jmp     {GET_RET:#x}
    ; ================= SM: Setter statt der zwei Originalbefehle ab 0x4001605a (d1 = Position, schon auf -1..97 begrenzt)
    SM:     jsr     P2S
            orig    {SET_HOOK:#x},10         ; verschobene Originalbefehle (Byte speichern)
            rts
    ''')
    code = adone(a, xl); check_cf(code, M_C)
    return code, dict(a.lab)


def tweak(img):
    parts, lab = build(img)
    W = Writes(img)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(EV_HOOK, EV_ORIG, jmp(lab['EV']) + bytes.fromhex("4e71"))
    W.hook(GET_HOOK, GET_ORIG, jmp(lab['GM']) + bytes.fromhex("4e71") * 7)
    W.hook(SET_HOOK, SET_ORIG, jsr(lab['SM']) + bytes.fromhex("4e714e71"))
    for va, ck, new in SMALL:
        W.hook(va, ck, bytes.fromhex(new))
    W.hook(DESC_MAX, struct.pack('>I', 63 << 8), struct.pack('>I', (NCOND - 1) << 8))
    W.hook(TXT_LEA, TXT_CK, jsr(lab['NMAP']) + bytes.fromhex("4e714e71"))
    W.hook(DSP_LEA, DSP_CK, jsr(lab['BMAP']))
    W.hook(PRC_AT, PRC_CK, jsr(lab['PRC']))                                       # smp21: Prozent nach FLAGS
    W.hook(NEG_LIM, NEG_CK, jsr(lab['NEGF']) + bytes.fromhex('4a80')              # jsr NEGF ; tst.l d0
           + bytes([0x67, NEG_SKIP - (NEG_LIM + 10)]) + bytes.fromhex('4e71'))     # beq.b ohne Strich ; nop
    return patch('fill2', 12, 'Fill 2 & Trig Conditions',
                 ["Hold PAGE and FUNC = Fill 2 instead of Fill 1 (also with fill latched by TRACK + PAGE).",
                  "New trig conditions FIL2 (plays only in Fill 2) and !FIL2 (plays except in Fill 2), right after FILL / !FILL.",
                  "During Fill 2, FILL trigs stay silent and !FILL trigs play.",
                  "Trig condition list reordered: A:B first (plus x:12 and x:16), then FILL / FIL2 / PTC / PRE / NEI / 1st / LST, percentages last.",
                  "PTC / !PTC: a newly chosen pattern is waiting (not chains, not Direct Jump); LST / !LST: the last pass before another pattern.",
                  "Erzeugt von v2/g2_fill2.py."], W,
                 requires=[], hooks=[f"{x:#x}" for x in (EV_HOOK, GET_HOOK, SET_HOOK, TXT_LEA, DSP_LEA, PRC_AT, NEG_LIM)],
                 symbols={k: f"{lab[k]:#x}" for k in ('EV', 'F2', 'GM', 'SM', 'XEV', 'PTC', 'LST', 'S2P', 'P2S', 'NMAP', 'BMAP', 'PRC', 'NEGF',
                                                     'POS2ST', 'ST2POS', 'FLAGS', 'OWNN', 'OWNB', 'S_FIL2', 'S_NFIL2')},
                 params={"cond_fil2": C_FIL2, "cond_nfil2": C_NFIL2, "ncond": NCOND, "order": ORDER, "fill_now": f"{FILL_NOW:#x}",
                         "func_byte": f"{func_bit(img)[0]:#x}", "func_bit": func_bit(img)[1]})


if __name__ == "__main__":
    img = stock()
    t = tweak(img)
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build(img)
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
