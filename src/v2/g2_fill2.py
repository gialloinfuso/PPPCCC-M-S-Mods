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
Speicher: Maske 0x40189930 (EV, F2, GM, SM, NMAP, BMAP, eigene Zeiger, Text). Kein RAM.
Aufruf: g2_fill2.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C

M_C = 0x40189930
SIZE = {M_C: 376}
NCOND = 66
C_FIL2, C_NFIL2 = 64, 65
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
    (SET_CL1, (2, 'f4fe429b77392bd272678ba7d265d4f6ecc18c97d38aaf8bd0eacc250312ed28'), "7041"),        # moveq #65,d0
    (SET_CL2, (2, '8500e6e3760f30ec85f007695ffcd97decb7a7f3219fe576e66e7fa4e877d73f'), "7241"),        # moveq #65,d1
    (TXT_LIM, (2, '14b4035526671323ac6a5c577b0aeaeaed54aa6c3596660e962437ef9d02a6e8'), "7441"),        # moveq #65,d2
    (DSP_LIM, (2, '8500e6e3760f30ec85f007695ffcd97decb7a7f3219fe576e66e7fa4e877d73f'), "7241"),        # moveq #65,d1
    (NEG_LIM, (2, 'a90648cc7894b37e690d6b58d5226d995aae8869a79d3edc2136e6dfdc108dda'), "7009"),        # moveq #9,d0
    (PRC_AT, (6, 'd9f5e3327fa41ddac8ee2607170249dd15971239e235d5f5867efef67008febe'), "70f6d0827214"),  # moveq #-10,d0 ; add.l d2,d0 ; moveq #20,d1
]
TXT_CK = (10, 'ba381dd36d95d2e6d21ecc3e46afb8a78135bc0b91945125fee3961349c14e32')
DSP_CK = (6, 'cd6ad9274dfa8679428daa40ef0257d2d97756bf1f2b0a0c60fbfdccececab1d')


def pos(sv):
    """gespeicherter Wert -> Position in der Liste"""
    if 0 <= sv <= 1: return sv
    if 2 <= sv <= 63: return sv + 2
    if sv in (C_FIL2, C_NFIL2): return sv - 62
    return sv


def stored(p):
    if 0 <= p <= 1: return p
    if 2 <= p <= 3: return p + 62
    if 4 <= p <= 65: return p - 2
    return p


def func_bit(img):
    idx = struct.unpack('>i', img[KEYIDX + 4 * C.KEY_FUNC - BASE:KEYIDX + 4 * C.KEY_FUNC - BASE + 4])[0]
    assert 0 <= idx and 1 <= (idx & 7) <= 7, idx
    return KEYMAP + (idx >> 3), idx & 7


def build(img):
    a = A(M_C); w, l = a.w, a.l32
    fb, fbit = func_bit(img)
    # ================= EV: statt moveq #63,d2 ; cmp.l d0,d2 ; bcs.w default. d2/d3 frei (gesichert), d1/a0/a1 erhalten.
    a.label('EV')
    w(0x7401, 0xB480); a.bcc(CS, 'ef')          # Bedingung > 1?
    a.bcc(BSR, 'F2'); a.bcc(EQ, 'orig')          # FILL / !FILL ohne Fill 2: Firmware
    w(0x7401, 0xB580)                           # Fill 2: FILL -> 1 (still), !FILL -> 0 (spielt)
    w(0x4EF9); l(EV_EXIT)
    a.label('ef')
    w(0x7400 | C_FIL2, 0xB480); a.bcc(EQ, 'f2')
    w(0x7400 | C_NFIL2, 0xB480); a.bcc(EQ, 'nf2')
    a.label('orig')
    a.orig(EV_HOOK, 4); a.bcc(CS, 'def')        # verschobene Originalbefehle (Grenze 63), dann wie die Firmware
    w(0x4EF9); l(EV_CONT)
    a.label('def'); w(0x4EF9); l(EV_DEF)
    a.label('f2')                               # FIL2: spielt nur in Fill 2
    a.bcc(BSR, 'F2'); w(0x7001, 0xB780)         # moveq #1,d0 ; eor.l d3,d0
    w(0x4EF9); l(EV_EXIT)
    a.label('nf2')                              # !FIL2: still in Fill 2
    a.bcc(BSR, 'F2'); w(0x2003)
    w(0x4EF9); l(EV_EXIT)
    # ================= F2: d3 = 1, wenn Fill an und FUNC gehalten (Z = !d3). Benutzt d2.
    a.label('F2')
    w(0x7600, 0x4A39); l(FILL_NOW); a.bcc(EQ, 'fr')
    w(0x1639); l(fb)                            # move.b Tastenbyte,d3
    w(0xE08B | (fbit << 9), 0x7401, 0xC682)     # lsr.l #bit,d3 ; moveq #1,d2 ; and.l d2,d3
    a.label('fr'); w(0x4E75)
    # ================= GM: Getter ab 0x40015ff6 (a2 = Objekt, d2 = Step): Byte lesen, -> Position, weiter 0x4001600a
    a.label('GM')
    a.orig(GET_HOOK, 20)                        # verschobene Originalbefehle: Daten holen, Byte lesen (aus dem Image)
    w(0x49C0)                                   # extb.l d0
    w(0x7202, 0xB280); a.bcc(GT, 'gd')          # < 2 (auch -1): bleibt
    w(0x723F, 0xB280); a.bcc(LT, 'gh')          # 2..63 -> +2
    w(0x5480); a.bcc(BRA, 'gd')
    a.label('gh')
    w(0x7200 | C_NFIL2, 0xB280); a.bcc(LT, 'gd')  # 64, 65 -> 2, 3
    w(0x723E, 0x9081)                           # moveq #62,d1 ; sub.l d1,d0
    a.label('gd'); w(0x4EF9); l(GET_RET)
    # ================= SM: Setter statt der zwei Originalbefehle ab 0x4001605a (d1 = Position, schon auf -1..65 begrenzt)
    a.label('SM')
    w(0x7002, 0xB081); a.bcc(GT, 'ss')          # < 2: bleibt
    w(0x7003, 0xB081); a.bcc(LT, 'sl')          # 2, 3 -> 64, 65
    w(0x703E, 0xD280); a.bcc(BRA, 'ss')
    a.label('sl'); w(0x5581)                    # 4..65 -> -2
    a.label('ss'); a.orig(SET_HOOK, 10); w(0x4E75)   # verschobene Originalbefehle (Byte speichern), zurueck
    # ================= NMAP: statt lea Namen,a0 ; lea (a0,d0.l*4),a0 (d0 = Position 0..65): a0 = Zeiger auf den Namen-Eintrag.
    #   d1 bleibt (Puffer). Position 2/3 -> eigene Zeiger (FIL2, !FIL2), sonst Eintrag der Firmware-Tabelle (Position -> Wert).
    a.label('NMAP')
    w(0x0C80); l(2); a.bcc(LT, 'nlo')           # cmpi.l #2,d0 ; blt
    w(0x0C80); l(3); a.bcc(GT, 'nhi')           # cmpi.l #3,d0 ; bgt
    w(0x5580, 0xE588, 0x41F9); l(0); fix_n = len(a.b) - 4   # subq.l #2,d0 ; lsl.l #2,d0 ; lea OWN_N,a0
    w(0xD1C0, 0x4E75)                           # adda.l d0,a0 ; rts
    a.label('nhi'); w(0x5580)                   # 4..65 -> Wert - 2
    a.label('nlo'); w(0xE588); a.orig(TXT_LEA, 6); w(0xD1C0, 0x4E75)   # lsl.l #2,d0 ; lea Namen,a0 (verschoben) ; adda.l d0,a0
    # ================= BMAP: statt lea Grundnamen,a0 (d2 = Position; danach liest die Firmware 0(a0,d2.l*4)). d1, d2 bleiben.
    a.label('BMAP')
    w(0x0C82); l(2); a.bcc(LT, 'bst')           # 0, 1: wie die Firmware
    w(0x0C82); l(NCOND - 1); a.bcc(HI, 'bst')   # > 65 (ungueltig): wie die Firmware
    w(0x0C82); l(3); a.bcc(GT, 'bhi')
    w(0x41F9); l(0); fix_b = len(a.b) - 4       # 2, 3: lea OWN_B-8,a0  (OWN_B + 4*(Pos-2) - 4*Pos)
    w(0x4E75)
    a.label('bhi'); w(0x41F9); l(BASEN0 - 8); w(0x4E75)   # 4..65: Eintrag Pos-2 der Firmware-Tabelle
    a.label('bst'); a.orig(DSP_LEA, 6); w(0x4E75)   # verschobener Originalbefehl: lea Grundnamen,a0
    code = bytearray(a.done()); check_cf(bytes(code), M_C)
    while len(code) % 4: code += b'\0'
    own_n = M_C + len(code); s_n = own_n + 16       # OWN_N: FIL2, !FIL2 ; OWN_B: FIL2, FIL2 ; Text '!FIL2' (FIL2 = ab +1)
    own_b = own_n + 8
    code += struct.pack('>4I', s_n + 1, s_n, s_n + 1, s_n + 1) + b'!FIL2\0'
    code[fix_n:fix_n + 4] = struct.pack('>I', own_n)
    code[fix_b:fix_b + 4] = struct.pack('>I', own_b - 8)
    return {M_C: bytes(code)}, dict(a.lab, OWN_N=own_n, OWN_B=own_b, S_NFIL2=s_n, S_FIL2=s_n + 1)


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
    return patch('fill2', 12, 'Fill 2',
                 ["Hold PAGE and FUNC = Fill 2 instead of Fill 1 (also with fill latched by TRACK + PAGE).",
                  "New trig conditions FIL2 (plays only in Fill 2) and !FIL2 (plays except in Fill 2), right after FILL / !FILL.",
                  "During Fill 2, FILL trigs stay silent and !FILL trigs play. Erzeugt von v2/g2_fill2.py."], W,
                 requires=[], hooks=[f"{x:#x}" for x in (EV_HOOK, GET_HOOK, SET_HOOK, TXT_LEA, DSP_LEA)],
                 symbols={k: f"{lab[k]:#x}" for k in ('EV', 'F2', 'GM', 'SM', 'NMAP', 'BMAP', 'OWN_N', 'OWN_B', 'S_FIL2', 'S_NFIL2')},
                 params={"cond_fil2": C_FIL2, "cond_nfil2": C_NFIL2, "fill_now": f"{FILL_NOW:#x}",
                         "func_byte": f"{func_bit(img)[0]:#x}", "func_bit": func_bit(img)[1]})


if __name__ == "__main__":
    img = stock()
    t = tweak(img)
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build(img)
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
