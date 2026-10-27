#!/usr/bin/env python3
"""v18-Bausteine: tabellengesteuerter Encoder-Haken (H4), Phaser (Reverb-Platz, Modus 3), Digital Delay (Delay-Platz, DMODE).
Phaser nach MXR Phase 90 / EHX Small Stone: 4 Allpass-Stufen (2 Notches), 50/50 trocken/Allpass intern,
  Stufen-Eckfrequenz 140 Hz .. 2 kHz exponentiell (Notches ca. 58..830 Hz und 340 Hz..4.8 kHz, Phase-90-Beispiel: 58/340 Hz bei 141 Hz),
  LFO sinusaehnlich, Speed (Size) 0..127 = 0.1 .. 6 Hz (quadratisch), Color (Tone) 0..127 = Feedback 0 .. 0.75
  (0 = Phase 90 'Script', mittel = 'Block'/Small-Stone 'Color'), rechts gegenphasiger LFO (Stereo).
Digital Delay nach Boss DD-2/DD-3 (Echo-Frequenzgang 40 Hz .. 7 kHz): im Schreibpfad 1-Pol-Tiefpass ~7.5 kHz und
  1-Pol-Hochpass ~120 Hz (jede Wiederholung wird schlanker, kein Matsch), Feedback-Kurve wie gemessen am Original
  ((3t - t^3)/2, 81 -> 0.83, 127 -> 1.0 endlos), Zeit wie das Original inkl. Notenwerte, bis 5.4 s, Zeile im Format des Originals (8 B/Frame, L=R)."""
import struct, sys, pathlib, math
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE
DTIME = 0x4005819E   # Delay-Zeit-Rechnung der Firmware (DSP); ihre Befehle kommen aus dem Image (A.orig), nicht aus dem Quelltext
from gen_chorusfx import check_cf, DESC, MODE, MODE2, COPY, HELD, SCRATCH
NE, EQ, PL, MI, LE, GE, HI, LS, CC, BRA, BSR = 0x6, 0x7, 0xA, 0xB, 0xF, 0xC, 0x2, 0x3, 0x4, 0x0, 0x1
DMODE = 0x404E9B5C      # gespeichert; Werkseinstellung der Firmware = 1 -> hier: 0 = Digital, sonst Original
M_H4, M_NX, M_DS, M_DL = 0x401625BC, 0x40160B6C, 0x40160E6C, 0x40185F48   # H4 liegt an der Stelle des alten H
M_PS, M_PP, M_PT = 0x40186238, 0x40189618, 0x4018AF88
M_W = 0x4018B1A8
STOCK, DNOTES, WRITE_DMA = 0x40057488, 0x4016AA28, 0x400573FA
D_HOOK, W_HOOK = 0x401B721C, 0x401B72A4
LINE, LMASK = 0x4A400000, 0x3FFFF      # Format wie das Original (8 B/Frame, L=R), untere Haelfte
DSTATE, DMAGIC = 0x4A33A180, 0x44494731      # +0 w, +4 cur, +8 Magic, +12 Tiefpass, +16 Hochpass-Tiefanteil
PSTATE, PMAGIC = 0x4A33A200, 0x50484153      # +0 Phase, +4 Magic, +8 L s0..s4, +28 R s0..s4, +48 aL, +52 aR
PH_MODE = 3

def w16(a, *x): a.w(*x)

# ---------------------------------------------------------------- H4: Encoder-Haken, Tabelle [enc, Byte, Max, Tasten]
def build_h4(entries, n_addr, ent_at, xor=False, slow_fn=None):
    """xor=True (1.13-Linie, Delay-Platz mit 4 Modi): invertierte Eintraege rechnen Wert = Byte XOR inv statt Max - Byte.
    slow_fn (1.13-Linie): nach erkannter Taste jsr slow_fn (d4 Drehung, d5 Ziel-Byte); d0 = 0 -> Drehung verschlucken, nichts aendern."""
    a = A(M_H4); w, l = a.w, a.l32
    a.label('H')
    w(0x4FEF, 0xFFEC)                       # lea -20(a7),a7
    w(0x48D7, 0x083C)                       # movem.l d2-d5/a3,(a7)
    w(0x792A, 0x0008)                       # mvs.b 8(a2),d4   Drehung
    w(0x4A84); a.bcc(EQ, 'exit')            # tst.l d4 ; beq exit
    w(0x262A, 0x0004)                       # move.l 4(a2),d3  Encoder
    w(0x47F9); l(0); fx_ent = len(a.b) - 4  # lea ENT,a3
    a.label('el')
    w(0x201B); a.bcc(MI, 'exit')            # move.l (a3)+,d0 ; bmi exit (Ende)
    w(0xB083); a.bcc(EQ, 'found')           # cmp.l d3,d0 ; beq found
    w(0x47EB, 0x0010); a.bcc(BRA, 'el')     # lea 16(a3),a3 ; bra el
    a.label('found')
    w(0x2A1B, 0x261B, 0x225B, 0x2413)       # d5 Byte ; d3 Max ; a1 Tasten ; d2 invertiert (Wert = Max - Byte)
    a.label('kl')
    w(0x7199); a.bcc(EQ, 'exit')            # mvz.b (a1)+,d0 ; beq exit (keine Taste)
    w(0x2F09, 0x2F00, 0x4EB9); l(HELD)      # move.l a1,-(a7) ; move.l d0,-(a7) ; jsr held
    w(0x588F, 0x225F, 0x4A80); a.bcc(EQ, 'kl')   # addq.l #4,a7 ; movea.l (a7)+,a1 ; tst.l d0 ; beq kl
    if slow_fn:
        w(0x4EB9); l(slow_fn); w(0x4A80); a.bcc(EQ, 'swallow')   # jsr SLOW ; tst.l d0 ; beq swallow
    w(0x2045, 0x7190)                       # movea.l d5,a0 ; mvz.b (a0),d0
    w(0x4A82); a.bcc(EQ, 'r1'); w(*((0xB580, 0x4E71) if xor else (0x9083, 0x4480)))   # tst.l d2 ; beq r1 ; eor.l d2,d0 ; nop | sub.l d3,d0 ; neg.l d0
    a.bcc(PL, 'r1'); w(0x7000)              # negativ (Muell) -> 0
    a.label('r1')
    w(0xB083); a.bcc(LE, 'v')               # cmp.l d3,d0 ; ble v
    w(0x2003)                               # move.l d3,d0 (ungueltig -> Max)
    a.label('v')
    w(0x2200, 0x4A84); a.bcc(LE, 'dec')     # move.l d0,d1 ; tst.l d4 ; ble dec
    w(0x5281); a.bcc(BRA, 'cl')             # addq.l #1,d1
    a.label('dec'); w(0x5381)               # subq.l #1,d1
    a.label('cl')
    w(0x4A81); a.bcc(PL, 'c1'); w(0x7200)   # tst.l d1 ; bpl c1 ; moveq #0,d1
    a.label('c1')
    w(0xB283); a.bcc(LE, 'c2'); w(0x2203)   # cmp.l d3,d1 ; ble c2 ; move.l d3,d1
    a.label('c2')
    w(0xB081); a.bcc(EQ, 'swallow')         # cmp.l d1,d0 ; beq swallow
    w(0x2001, 0x4A82); a.bcc(EQ, 'w1')      # move.l d1,d0 ; tst.l d2 ; beq w1
    w(*((0xB580, 0x4E71) if xor else (0x2003, 0x9081)))   # eor.l d2,d0 ; nop | move.l d3,d0 ; sub.l d1,d0   (Byte = Wert ^ inv | Max - Wert)
    a.label('w1')
    w(0x13C0); l(SCRATCH)                   # move.b d0,SCRATCH
    w(0x4878, 0x0001, 0x4879); l(SCRATCH)   # pea 1.w ; pea SCRATCH
    w(0x2F05, 0x4EB9); l(COPY)              # move.l d5,-(a7) ; jsr COPY (Einstellungsblock + Pruefsumme)
    w(0x4FEF, 0x000C)                       # lea 12(a7),a7
    w(0x4EB9); l(n_addr)                    # jsr N (Namen sofort)
    a.label('swallow'); w(0x7800)           # moveq #0,d4
    a.label('exit')
    w(0x2204, 0x4CD7, 0x083C, 0x4FEF, 0x0014)   # move.l d4,d1 ; movem.l (a7),d2-d5/a3 ; lea 20(a7),a7
    w(0x205F, 0x2F01, 0x4ED0)               # movea.l (a7)+,a0 ; move.l d1,-(a7) ; jmp (a0)
    code = bytearray(a.done()); check_cf(bytes(code), M_H4)
    ent = ent_at; keys_off = 20 * len(entries) + 4
    kb = b''; rows = b''
    for e in entries:
        enc, byte, mx, keys = e[:4]; inv = e[4] if len(e) > 4 else 0
        rows += struct.pack('>5I', enc, byte, mx, ent + keys_off + len(kb), inv); kb += bytes(keys) + b'\0'
    table = rows + struct.pack('>i', -1) + kb
    code[fx_ent:fx_ent + 4] = struct.pack('>I', ent)
    assert len(code) <= 280, len(code)
    return bytes(code), a.lab['H'], table

# ---------------------------------------------------------------- N_EXTRA: Delay-Namen nach DMODE
DNAMES = [b"Digi Send", b"DIGS", b"Digi Time", b"TIME", b"Digi Fdbk", b"FDBK"]
def build_nx(img):
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(DESC(26) + 0x2C), rd(DESC(26) + 0x34), rd(DESC(37) + 0x2C), rd(DESC(37) + 0x34), rd(DESC(38) + 0x2C), rd(DESC(38) + 0x34)]
    a = A(M_NX); w, l = a.w, a.l32
    a.label('NX')
    w(0x41F9); l(DMODE)                     # lea DMODE,a0
    w(0x7190, 0x7200, 0x4A80); a.bcc(NE, 'z')   # mvz.b (a0),d0 ; moveq #0,d1 ; tst.l d0 ; bne z (Original)
    w(0x7218)                               # moveq #24,d1
    a.label('z')
    w(0x43F9); l(0); fx = len(a.b) - 4      # lea ROWS,a1
    w(0xD3C1)                               # adda.l d1,a1
    w(0x41F9); l(DESC(26) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41F9); l(DESC(37) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41E8, 0x0038, 0x2099, 0x2159, 0x0008)
    w(0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_NX)
    while len(code) % 4: code += b'\0'
    rows = M_NX + len(code); at = rows + 48; ptr = []; strs = b''
    for s in DNAMES: ptr.append(at + len(strs)); strs += s + b'\0'
    code += struct.pack('>6I', *orig) + struct.pack('>6I', *ptr) + strs
    code[fx:fx + 4] = struct.pack('>I', rows)
    assert len(code) <= 280, len(code)
    return bytes(code), a.lab['NX']

# ---------------------------------------------------------------- Digital Delay
def build_dl():
    a = A(M_DL); w, l = a.w, a.l32
    # d3 w, d4 cur, d5 Zaehler, d6 Tiefpass, a6 Hochpass-Tiefanteil, a0 in, a1 out, a2 LINE, a3 Zustand, a4 Ziel-T, a5 g (Q15)
    a.label('loop')
    w(0x200C, 0x9084, 0x2E00, 0xE087, 0xEA87); a.bcc(NE, 'add')   # Gleiten wie das Original (diff>>13)
    w(0x4A80); a.bcc(EQ, 'nost')
    w(0x2203, 0x0281); l(3); a.bcc(NE, 'nost')
    w(0x7E01, 0x4A80); a.bcc(PL, 'add'); w(0x7EFF)
    a.label('add'); w(0xD887)
    a.label('nost')
    w(0x2003, 0x9084, 0x0280); l(LMASK)     # move.l d3,d0 ; sub.l d4,d0 ; andi.l #MASK,d0
    w(0xE788, 0x2232, 0x0800)               # lsl.l #3,d0 ; move.l 0(a2,d0.l),d1    y
    w(0x2E0D)                               # move.l a5,d7          g
    w(0x2001, 0xE080, 0xEE80, 0x4C07, 0x0800)   # move.l d1,d0 ; asr #8 ; asr #7 ; muls.l d7,d0   (hoch)
    w(0x2401, 0x0282); l(0x7FFF)            # move.l d1,d2 ; andi.l #$7fff,d2
    w(0x4C07, 0x2800, 0xE082, 0xEE82, 0xD082)   # muls.l d7,d2 ; asr #8 ; asr #7 ; add.l d2,d0   g*y
    w(0x2418, 0xE682, 0x2E18, 0xE687, 0xD487)   # move.l (a0)+,d2 ; asr #3 ; move.l (a0)+,d7 ; asr #3 ; add.l d7,d2   x
    w(0xD082, 0x4C80)                       # add.l d2,d0 ; sats.l d0     s = x + g*y
    w(0x2400, 0xE282, 0x2E06, 0xE287, 0x9487)   # Tiefpass: d=(s>>1)-(lp>>1)
    w(0x2E02, 0xE487, 0xD487, 0xDC82)       #   d += d>>2 ; lp += d   (~7.5 kHz)
    w(0x2406, 0x2E0E, 0x9487)               # Hochpass: move.l d6,d2 ; move.l a6,d7 ; sub.l d7,d2   (lp - tief)
    w(0x2002, 0xEC80, 0xDE80, 0x2C47, 0x9480)   # move.l d2,d0 ; asr.l #6,d0 ; add.l d0,d7 ; movea.l d7,a6 ; sub.l d0,d2  (~120 Hz)
    w(0x2003, 0xE788, 0x2582, 0x0800, 0x2582, 0x0804)   # move.l d3,d0 ; lsl.l #3,d0 ; L und R schreiben
    w(0xD281, 0x4C81, 0xD281, 0x4C81)       # add.l d1,d1 ; sats ; add.l d1,d1 ; sats   (x4 = Einheitspegel)
    w(0x22C1, 0x22C1)                       # move.l d1,(a1)+ (L) ; move.l d1,(a1)+ (R)
    w(0x5283, 0x0283); l(LMASK)             # addq.l #1,d3 ; andi.l #MASK,d3
    w(0x5385); a.bcc(NE, 'loop')
    w(0x2683, 0x2744, 0x0004, 0x2746, 0x000C, 0x274E, 0x0010)   # w, cur, lp, tief speichern
    w(0x4CD7, 0x7CFC, 0x4FEF, 0x002C, 0x4E75)
    code = a.done(); check_cf(code, M_DL); assert len(code) <= 272, len(code)
    return code

def build_ds(loop_at):
    a = A(M_DS); w, l = a.w, a.l32
    a.label('D')
    w(0x41F9); l(DMODE); w(0x7390, 0x4A81); a.bcc(EQ, 'dd')    # lea DMODE,a0 ; mvz.b (a0),d1 ; tst.l d1 ; beq dd (0 = Digital)
    w(0x4EF9); l(STOCK)
    a.label('dd')
    w(0x4FEF, 0xFFD4, 0x48D7, 0x7CFC)       # lea -44(a7),a7 ; movem.l d2-d7/a2-a6,(a7)
    w(0x206F, 0x0038)                       # movea.l 56(a7),a0   Parameter
    w(0x7F68, 0x0002, 0xE087, 0x4A87); a.bcc(PL, 'p1'); w(0x7E00)   # Fdbk
    a.label('p1')
    w(0x0C87); l(127); a.bcc(LE, 'p2'); w(0x7E7F)
    a.label('p2')
    w(0x203C); l(258); w(0x4C00, 0x7800)    # t15 = v*258
    w(0x2007, 0x4C07, 0x0800, 0xE080, 0xEE80)   # t^2
    w(0x4C07, 0x0800, 0xE080, 0xEE80)       # t^3
    w(0x2207, 0xDE87, 0xDE81, 0x9E80, 0xE287)   # g = (3t - t^3)/2
    w(0x2A47)                               # movea.l d7,a5
    w(0x7150); a.orig(DTIME, 6); w(0x760A); a.orig(DTIME + 10, 6)   # Zeit wie die Firmware (Befehle aus dem Image)
    a.orig(DTIME + 20, 6); w(0x4EB9); l(DNOTES)
    a.orig(DTIME + 32, 14)
    w(0x0C80); l(0x3FC00); a.bcc(LS, 'p3'); w(0x203C); l(0x3FC00)
    a.label('p3')
    w(0x0C80); l(32); a.bcc(CC, 'p4'); w(0x7020)
    a.label('p4')
    w(0x2840)                               # movea.l d0,a4   Ziel-T
    w(0x47F9); l(DSTATE)
    w(0x202B, 0x0008, 0x0C80); l(DMAGIC); a.bcc(EQ, 'ok')
    w(0x203C); l(DMAGIC); w(0x2740, 0x0008)
    w(0x7000, 0x2680, 0x2740, 0x000C, 0x2740, 0x0010)   # w = lp = tief = 0
    w(0x200C, 0x2740, 0x0004)               # cur = Ziel
    a.label('ok')
    w(0x2613, 0x282B, 0x0004, 0x2C2B, 0x000C, 0x2C6B, 0x0010)   # w, cur, lp, tief
    w(0x7A20, 0x226F, 0x0030, 0x206F, 0x0034)   # moveq #32,d5 ; out ; in
    w(0x45F9); l(LINE); w(0x4EF9); l(loop_at)
    code = a.done(); check_cf(code, M_DS); assert len(code) <= 280, len(code)
    return code, a.lab['D']

def build_w():
    a = A(M_W); w, l = a.w, a.l32
    a.label('W')                            # Schreib-DMA des Originals: im Digital-Modus in die obere Haelfte
    w(0x41F9); l(DMODE); w(0x7190, 0x4A80); a.bcc(NE, 'wgo')
    w(0x2039); l(0x8000B988); w(0x0080); l(0x40000); w(0x23C0); l(0x8000B988)
    a.label('wgo'); w(0x4EF9); l(WRITE_DMA)
    code = a.done(); check_cf(code, M_W); return code, a.lab['W']

# ---------------------------------------------------------------- Phaser
FMIN, FMAX, FS = 100.0, 4000.0, 48000.0
def coef_table():
    t = []
    for i in range(33):
        f = FMIN * (FMAX / FMIN) ** (i / 32)
        k = math.tan(math.pi * f / FS); t.append(round((k - 1) / (k + 1) * 32768))
    return t

def build_pp():
    a = A(M_PP); w, l = a.w, a.l32
    # a0 in, a1 out (eigener Kanal), a4 Ende in, d7 a (Q15), a2 fb (Q15), d2..d6 = s0..s4 ; frei: d0, d1, a5, a6
    a.label('P')
    w(0x2006, 0xE080, 0xEE80, 0x220A, 0x4C01, 0x0800)   # fbk = (s4>>15)*fb
    w(0x2218, 0xE881, 0x2C41, 0x2218, 0xE881, 0xDDC1)   # x = L/16 + R/16 -> a6 (Reserve fuer Resonanz)
    w(0xD08E)                               # add.l a6,d0   u
    for sb, sa in ((2, 3), (3, 4), (4, 5), (5, 6)):
        w(0x2A40)                           # movea.l d0,a5        Eingang merken
        w(0x2200, 0x9280 | sa)              # move.l d0,d1 ; sub.l sA,d1   v
        w(0x2001, 0xE080, 0xEE80, 0x4C07, 0x0800)   # (v>>15)*a
        w(0x0281); l(0x7FFF)                # andi.l #$7fff,d1
        w(0x4C07, 0x1800, 0xE081, 0xEE81, 0xD081)   # ((v&$7fff)*a)>>15 ; add
        w(0xD080 | sb)                      # add.l sB,d0         y
        w(0x200D | (sb << 9))               # move.l a5,sB        sB = Eingang
    w(0x2C00)                               # move.l d0,d6   s4 = y3
    w(0x220E, 0xD280, 0xD281, 0x4C81, 0xD281, 0x4C81)   # out = (x + y3) * 4
    w(0x2281, 0x5089)                       # move.l d1,(a1) ; addq.l #8,a1
    w(0xB1CC); a.bcc(NE, 'P')               # cmpa.l a4,a0 ; bne P
    w(0x4E75)
    code = a.done(); check_cf(code, M_PP); assert len(code) <= 272, len(code)
    return code, a.lab['P']

def build_coef():
    a = A(M_PT); w, l = a.w, a.l32
    a.label('coef')                         # d0 Phase -> d7 Koeffizient (Q15); veraendert d1-d3, a0
    w(0x2200); a.bcc(PL, 'cp'); w(0x4681)
    a.label('cp')
    w(0x0481); l(0x40000000); w(0xE081, 0xEE81)   # Dreieck +-32768
    w(0x2401, 0x4C02, 0x2800, 0xE082, 0xEE82, 0x4C01, 0x2800, 0xE082, 0xEE82)   # t^3
    w(0x2601, 0xD281, 0xD283, 0x9282, 0xE281)   # (3t - t^3)/2
    w(0x0681); l(32768)
    w(0x0C81); l(65535); a.bcc(LE, 'c1'); w(0x223C); l(65535)
    a.label('c1')
    w(0x2401, 0x760B, 0xE6AA, 0x0281); l(0x7FF)   # idx = p>>11 ; frac = p & $7ff
    w(0x41F9); l(0); fx = len(a.b) - 4; w(0xD482)         # lea TAB,a0 ; add.l d2,d2
    w(0x7770, 0x2800, 0x7F70, 0x2802)       # mvs.w 0(a0,d2.l),d3 ; mvs.w 2(a0,d2.l),d7
    w(0x9E83, 0x4C01, 0x7800, 0xE087, 0xE687, 0xDE83)   # d7 = t0 + ((t1-t0)*frac >> 11)
    w(0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_PT)
    while len(code) % 2: code += b'\0'
    tab_at = M_PT + len(code); code += struct.pack('>33h', *coef_table())
    code[fx:fx + 4] = struct.pack('>I', tab_at); assert len(code) <= 272, len(code)
    return bytes(code), a.lab['coef']

def build_ps(pass_at, coef_at):
    a = A(M_PS); w, l = a.w, a.l32
    a.label('PH')
    w(0x4FEF, 0xFFD4, 0x48D7, 0x7CFC)
    w(0x206F, 0x0038)                       # Parameter
    w(0x71D0, 0xE088, 0x73E8, 0x0002, 0xE089)   # S (d0), C (d1)
    w(0x2400, 0x4C00, 0x2800, 0x7621, 0x4C03, 0x2800)   # d2 = S*S*33
    w(0x0682); l(8948); w(0xEB8A)           # + 8948 ; lsl.l #5,d2   (je Block)
    w(0x263C); l(193); w(0x4C03, 0x1800, 0x2441)   # fb = C*193 -> a2
    w(0x47F9); l(PSTATE)
    w(0x202B, 0x0004, 0x0C80); l(PMAGIC); a.bcc(EQ, 'ok')
    w(0x204B, 0x700B)                       # movea.l a3,a0 ; moveq #11,d0
    a.label('cl'); w(0x4298, 0x5380); a.bcc(PL, 'cl')   # 12 Longs loeschen (Phase, Zustaende)
    w(0x203C); l(PMAGIC); w(0x2740, 0x0004)  # Magic setzen
    a.label('ok')
    w(0x2013, 0xD082, 0x2680)               # Phase += Zuwachs
    w(0x4EB9); l(coef_at); w(0x2747, 0x0030)   # jsr COEF ; aL
    w(0x2013, 0x0680); l(0x80000000)        # Gegenphase
    w(0x4EB9); l(coef_at); w(0x2747, 0x0034)   # aR
    for ch, so, sa in ((0, 8, 0x30), (4, 28, 0x34)):
        w(0x206F, 0x0034, 0x226F, 0x0030)   # in, out
        if ch: w(0x5889)                    # addq.l #4,a1
        w(0x49E8, 0x0100)                   # lea 256(a0),a4
        w(0x2E2B, sa)                       # move.l a(a3),d7
        w(0x4CEB, 0x007C, so)               # movem.l so(a3),d2-d6
        w(0x4EB9); l(pass_at)
        w(0x48EB, 0x007C, so)               # movem.l d2-d6,so(a3)
    w(0x4CD7, 0x7CFC, 0x4FEF, 0x002C, 0x4E75)
    code = a.done(); check_cf(code, M_PS); assert len(code) <= 272, len(code)
    return code, a.lab['PH']

def build_all(img, n_addr_cb=None):
    dl = build_dl(); ds, d_addr = build_ds(M_DL); wc, w_addr = build_w()
    pp, p_addr = build_pp(); tab = coef_table()
    pt, coef_addr = build_coef()
    ps, ph_addr = build_ps(p_addr, coef_addr)
    nx, nx_addr = build_nx(img)
    return dict(dl=dl, ds=ds, wc=wc, d_addr=d_addr, w_addr=w_addr, pp=pp, ps=ps, ph_addr=ph_addr,
                pt=pt, coef_addr=coef_addr, nx=nx, nx_addr=nx_addr, tab=tab)
