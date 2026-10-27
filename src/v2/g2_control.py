#!/usr/bin/env python3
"""Mod 'control-mode' (v2): CONTROL ALL relativ oder absolut. Braucht nur 'core'.
Umschalten: TRACK halten + SETTINGS kurz druecken (Loslassen ohne Drehung dazwischen) -> Popup 'Control' / 'All' +
  'Absolute' / 'Relative'. Global im Einstellungsblock (CTRL_MODE 0x404e9b5d, beim Ausschalten gespeichert);
  0x5a = absolut, alles andere = relativ (Firmware; nach dem Zuruecksetzen 0, v1-Reste 1..4 ebenfalls relativ).
Relativ = Firmware: jeder Track eigener Wert + Drehung, am Anschlag bleibt er stehen (der Setter klemmt).
Absolut: der ausgewaehlte Track macht den Schritt wie in der Firmware, alle anderen Tracks bekommen genau seinen neuen Wert
  (geklemmt auf ihren Bereich).
Betrifft:
  - TRACK + Regler (ParameterPageView, vtable 0x4010052c + 0x5c = 0x4001d6e4, die Firmware-Schleife ueber 6 Tracks):
    Eintrag 0x40100588 -> CA; relativ springt CA in die Firmware-Funktion.
  - TRACK + LEVEL/DATA (Lautstaerke) und FUNC + TRACK + LEVEL/DATA (Pan) im Hauptbildschirm (0x4001aa4e): Haken an den
    Anfaengen der Lautstaerke- und Pan-Zweige 0x4001ab7a (LV) und 0x4001aaec (LP); die Schleifen selbst bleiben unberuehrt
    (ihr Sprungziel liegt 4 Byte hinter dem Schleifenanfang, dort ist kein Platz fuer einen Haken).
  - groove liest dasselbe Byte fuer TRACK + SETTINGS/MACHINE + Swing (Humanize aller Tracks).
Gesten: Tasten-Slot 0 des Cores (SETTINGS Druecken / Loslassen) = CMK; Encoder-Slot 5 = CME (SETTINGS gehalten und ein
  Regler gedreht -> CM_SU, dann schaltet das Loslassen nicht um).
Speicher: Masken 0x40182b38 (CA, PO, LV), 0x40182e28 (LP, CMK, CME, Texte). RAM CM_SU 0x4a33c3a8, CM_SCR 0x4a33c3a9.
Aufruf: g2_control.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core

M_A, M_B = 0x40182B38, 0x40182E28
SIZE = {M_A: 376, M_B: 376}
VT_SLOT, VT_ORIG = 0x40100588, 0x4001D6E4          # ParameterPageView vtable +0x5c: CONTROL ALL
LV_HOOK, LV_BACK = 0x4001AB7A, 0x4001AB80         # Lautstaerke: lea 0x40009ca0,a3 (Getter) ; danach lea Setter,a2
LP_HOOK, LP_BACK = 0x4001AAEC, 0x4001AAF2         # Pan: lea 0x400097f0,a2 (Klang-Objekt) ; danach lea 0x4000b274,a3
LV_ORIG, LP_ORIG = (6, 'a9582d71004325d3910cf00e3f68321081f3275f410d6fb86f72c9e44125efec'), (6, '374b55394d625229746501ff009282acfaca2cf2afe019f5f928d4e0a75a5288')   # Laenge + SHA-256
VGET, VSET, SOBJ = 0x40009CA0, 0x4000A3AE, 0x400097F0
L_END = 0x4001ABCE                                # Ende des Encoder-Handlers (move.b d5,d0 ; Register zurueck)
SETP = 0x4000B274                                 # Parameter setzen (obj, param, wert, track, f1, f2) -> Wert (Getter)
PAN = 0x1C
TXT = {'l1': "Control", 'l2': "All", 'abs': "Absolute", 'rel': "Relative"}
ABS, MODE, SU, SCR = C.CTRL_ABS, C.CTRL_MODE, C.CM_SU, C.CM_SCR


def is_abs(w, l):
    """mvz.b CTRL_MODE,d0 ; moveq #ABS,d1 ; cmp.l d1,d0  (Z = absolut; zerstoert d0, d1)"""
    w(0x71B9); l(MODE); w(0x7200 | ABS, 0xB081)


def build_a():
    a = A(M_A); w, l = a.w, a.l32
    # ---------------- CA(this, Encoder, Drehung): statt 0x4001d6e4
    a.label('CA')
    is_abs(w, l); a.bcc(EQ, 'abs')
    w(0x4EF9); l(VT_ORIG)                       # relativ: Firmware
    a.label('abs')
    w(0x4FEF, 0xFFE0, 0x48D7, 0x0CFC)           # lea -32(a7),a7 ; movem.l d2-d7/a2-a3,(a7)
    w(0x246F, 0x0024, 0x2C2F, 0x0028, 0x2E2F, 0x002C)   # a2 = this ; d6 = Encoder ; d7 = Drehung
    w(0x4EB9); l(C.SEL_A); w(0x2F00, 0x4EB9); l(C.SEL_B); w(0x2F00, 0x4EB9); l(C.SEL_C); w(0x508F, 0x2800)  # d4 = Track
    w(0x4878, C.KEY_FUNC, 0x4EB9); l(C.HELD)    # FUNC wie die Firmware: 0 / 1
    w(0x588F, 0x4A80, 0x56C0, 0x7100, 0x4480, 0x2A00)
    w(0x2404); a.bcc(BSR, 'PO')                 # ausgewaehlter Track: d3 = Parameter, d0 = Objekt
    w(0x2240, 0x2051)                           # movea.l d0,a1 ; movea.l (a1),a0
    w(0x42A7, 0x42A7, 0x42A7, 0x42A7, 0x2F02, 0x2F07, 0x2F03, 0x2F00)
    w(0x2068, 0x0020, 0x4E90, 0x4FEF, 0x0020)   # obj->vt[0x20](obj, param, Drehung, track, 0,0,0,0) -> neuer Wert
    w(0x2E00, 0x7400)                           # d7 = Zielwert ; d2 = 0
    a.label('lp')
    w(0xB484); a.bcc(EQ, 'nx')                  # cmp.l d4,d2 ; beq (ausgewaehlter Track schon gesetzt)
    a.bcc(BSR, 'PO')
    w(0x2640, 0x2053, 0x42A7, 0x2F07, 0x2F03, 0x2F0B)   # a3 = obj ; Zielwert auf erlaubten Wert des Tracks:
    w(0x2068, 0x0014, 0x4E90, 0x4FEF, 0x0010)   # obj->vt[0x14](obj, param, Ziel, 0) (klemmt, naechster erlaubter Wert)
    w(0x42A7, 0x42A7, 0x2F02, 0x2F00, 0x2F03, 0x2F0B, 0x4EB9); l(SETP); w(0x4FEF, 0x0018)   # setzen wie die Firmware
    a.label('nx')
    w(0x5282, 0x7006, 0xB082); a.bcc(NE, 'lp')
    w(0x4CD7, 0x0CFC, 0x4FEF, 0x0020, 0x4E75)
    # ---------------- PO: d2 = Track -> d3 = Parameter unter dem Regler, d0 = Objekt (a2 this, d5 FUNC, d6 Encoder)
    a.label('PO')
    w(0x2052, 0x2068, 0x007C)                   # movea.l (a2),a0 ; movea.l $7c(a0),a0
    w(0x2F02, 0x2F05, 0x2F06, 0x2F0A, 0x4E90, 0x4FEF, 0x0010, 0x2600)
    w(0x2052, 0x2068, 0x0080)
    w(0x2F03, 0x2F02, 0x2F0A, 0x4E90, 0x4FEF, 0x000C, 0x4E75)
    # ---------------- LV (Haken 0x4001ab7a): Lautstaerke. d2 Kit, d3 Track, d6.b TRACK gehalten, d7.w Schritt
    a.label('LV')
    a.orig(LV_HOOK, 6)                          # verschobener Originalbefehl: lea Getter,a3
    w(0x4A06); a.bcc(EQ, 'lo')                  # ohne TRACK: Firmware
    is_abs(w, l); a.bcc(EQ, 'la')
    a.label('lo')
    w(0x4EF9); l(LV_BACK)                       # relativ: Firmware
    a.label('la')
    w(0x45F9); l(VSET); w(0x7F47)             # lea Setter,a2 ; mvs.w d7,d7
    w(0x2F03, 0x2F02, 0x4E93, 0x508F, 0xD087)   # get(kit, track) + Schritt
    w(0x4878, 0x0001, 0x2F00, 0x2F03, 0x2F02, 0x4E92, 0x4FEF, 0x0010)   # set(kit, track, v, 1) (klemmt)
    w(0x2F03, 0x2F02, 0x4E93, 0x508F, 0x2E00, 0x7600)                   # d7 = get(kit, track) ; d3 = 0
    a.label('lb')
    w(0x4878, 0x0001, 0x2F07, 0x2F03, 0x2F02, 0x4E92, 0x4FEF, 0x0010)
    w(0x5283, 0x7006, 0xB083); a.bcc(NE, 'lb')
    w(0x4EF9); l(L_END)
    code = a.done(); check_cf(code, M_A)
    return code, dict(a.lab)


def build_b():
    cs = core.sym()
    a = A(M_B); w, l = a.w, a.l32
    # ---------------- LP (Haken 0x4001aaec): Pan. a2 = Klang-Objekt(kit, track), a3 = Setter 0x4000b274
    a.label('LP')
    a.orig(LP_HOOK, 6)                          # verschobener Originalbefehl: lea Klang-Objekt,a2
    w(0x4A06); a.bcc(EQ, 'po')
    is_abs(w, l); a.bcc(EQ, 'pa')
    a.label('po')
    w(0x4EF9); l(LP_BACK)
    a.label('pa')
    w(0x47F9); l(SETP); w(0x7F47)               # lea 0x4000b274,a3 ; mvs.w d7,d7
    w(0x2F03, 0x2F02, 0x4E92, 0x508F, 0x2C00)   # d6 = Objekt des Tracks
    w(0x2240, 0x2051, 0x4878, PAN, 0x2F00, 0x2068, 0x001C, 0x4E90, 0x508F, 0xD087)   # Getter(obj, PAN) + Schritt
    w(0x4878, 0x0001, 0x42A7, 0x2F03, 0x2F00, 0x4878, PAN, 0x2F06, 0x4E93, 0x4FEF, 0x0018, 0x2E00, 0x7600)
    a.label('pb')
    w(0x2F03, 0x2F02, 0x4E92, 0x508F)
    w(0x4878, 0x0001, 0x42A7, 0x2F03, 0x2F07, 0x4878, PAN, 0x2F00, 0x4E93, 0x4FEF, 0x0018)
    w(0x5283, 0x7006, 0xB083); a.bcc(NE, 'pb')
    w(0x4EF9); l(L_END)
    # ---------------- CMK: Tasten-Slot (d1 = 0 Druecken / 1 Loslassen) ; Loslassen + TRACK gehalten + unbenutzt -> umschalten
    a.label('CMK')
    w(0x4A81); a.bcc(NE, 'rel')
    w(0x4239); l(SU); w(0x7000, 0x4E75)         # Druecken: clr.b SU
    a.label('rel')
    w(0x4A39); l(SU); a.bcc(NE, 'no')
    w(0x4878, C.KEY_TRACK, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'no')
    is_abs(w, l); a.bcc(NE, 'wr')               # bisher relativ -> d1 = ABS
    w(0x7200)                                   # bisher absolut -> 0
    a.label('wr')
    w(0x13C1); l(SCR)
    w(0x4878, 0x0001, 0x4879); l(SCR); w(0x4879); l(MODE); w(0x4EB9); l(C.COPY); w(0x4FEF, 0x000C)
    w(0x41F9); l(0); fx_rel = len(a.b) - 4
    w(0x4A39); l(SCR); a.bcc(EQ, 'tx')
    w(0x41F9); l(0); fx_abs = len(a.b) - 4
    a.label('tx')
    w(0x2208, 0x41F9); l(0); fx_l1 = len(a.b) - 4
    w(0x43F9); l(0); fx_l2 = len(a.b) - 4
    w(0x7000 | C.OV_TEXT, 0x4EB9); l(cs['OVS'])
    w(0x7001, 0x4E75)
    a.label('no')
    w(0x4239); l(SU); w(0x7000, 0x4E75)
    # ---------------- CME: Encoder-Slot; SETTINGS gehalten -> SU (das Loslassen schaltet dann nicht um) ; nie 'meins'
    a.label('CME')
    w(0x4878, C.KEY_SET, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'ce')
    w(0x7001, 0x13C0); l(SU)
    a.label('ce')
    w(0x7000, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_B)
    at = {}
    for k, s in TXT.items():
        at[k] = M_B + len(code); code += s.encode() + b'\0'
    for pos, k in ((fx_rel, 'rel'), (fx_abs, 'abs'), (fx_l1, 'l1'), (fx_l2, 'l2')):
        code[pos:pos + 4] = struct.pack('>I', at[k])
    return bytes(code), dict(a.lab, **{'T_' + k.upper(): v for k, v in at.items()})


def build():
    ca, la = build_a(); cb, lb = build_b()
    lab = dict(la); lab.update(lb)
    return {M_A: ca, M_B: cb}, lab


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(VT_SLOT, struct.pack('>I', VT_ORIG), struct.pack('>I', lab['CA']))
    W.hook(LV_HOOK, LV_ORIG, jmp(lab['LV']))
    W.hook(LP_HOOK, LP_ORIG, jmp(lab['LP']))
    core.slot_write(W, 'control-mode', lab['CME'])
    core.kslot_write(W, 'control-mode', lab['CMK'])
    return patch('control-mode', 10, 'Control mode: CONTROL ALL relative or absolute',
                 ["Hold TRACK + tap SETTINGS: CONTROL ALL switches between Relative (firmware: every track moves by the same",
                  "amount and stops at its limit) and Absolute (all tracks take the new value of the selected track).",
                  "Applies to TRACK + knob, TRACK + LEVEL (volume), FUNC + TRACK + LEVEL (pan) and the humanize of groove.",
                  "Global setting, kept after power-off. Erzeugt von v2/g2_control.py."],
                 W, requires=['core'], hooks=[f"{VT_SLOT:#x}", f"{LV_HOOK:#x}", f"{LP_HOOK:#x}"],
                 memory=[{"va": f"{SU:#x}", "size": 2, "ram": True, "use": "SETTINGS used since press, byte for COPY"}],
                 settings=[f"{MODE:#x} ({ABS:#x} absolute, anything else relative)"],
                 symbols={k: f"{v:#x}" for k, v in lab.items() if k[0].isupper()},
                 params={"slot": C.SLOT['control-mode'], "kslot": C.KSLOT['control-mode'], "abs": ABS, "texts": TXT})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items()})
