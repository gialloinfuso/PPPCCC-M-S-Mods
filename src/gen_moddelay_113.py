#!/usr/bin/env python3
"""Tweak 'mod-delays' fuer die OFFIZIELLE Model:Cycles OS 1.13: VIBDEL und CHODEL auf dem Delay-Platz (Idee: EHX Memory Man).
Setzt delay-notes, chorus, phaser, digi-delay, razer voraus (erweitert Delay-Weiche, Namen, H4).

Bedienung:
  TRACK + Delay Time:        Delay -> Digital -> VIBDEL -> CHODEL (Byte 0x404e9b5c: 1 Original, 0 Digital, 3 VIBDEL, 2 CHODEL;
                             H4 rechnet fuer diese Zeile Wert = Byte XOR 1, damit Werkseinstellung 1 = Original bleibt)
  SETTINGS + DELAY SEND:     Speed (0..127, Byte 0x404e9b5b; Stock setzt es beim Reset auf 1 und liest es nie), Anzeige
                             'SPEED nn' 1.5 s auf dem Hauptbildschirm (gen_overlay_113). Eigener Encoder-Haken SP vor H4.
                             Jede Rastung ruft consume(SETTINGS): Loslassen oeffnet dann nicht das Menue. Das Ereignis wird
                             ganz verschluckt (Sprung nach 0x400081e0), die Firmware sieht es nicht (v2 gab Schritt 0 weiter ->
                             Parameter-Popup -> Anzeige unsichtbar). Langes Halten von SETTINGS (Firmware: Projekt speichern
                             nach 533 ms) speichert jetzt erst beim Loslassen und nur ohne Drehung (gen_overlay_113.build_keys).
                             (v1: TRACK + FUNC + Delay Time, v2: TRACK + DELAY SEND - nahm CONTROL ALL den Regler weg.)
  Effektwahl (Reverb- und Delay-Platz) gebremst: H4 schaltet erst nach SLOW_N Rastungen eine Stufe (gen_overlay_113.SLOW).
  Delay Time / FUNC + Delay Time / Send wie beim Digital Delay (Zeit inkl. Notenwerte, Feedback-Kurve wie Digital).
Klang (je Frame, Zeile 0x4a400000 wie Digital Delay, 8 B/Frame L = R):
  VIBDEL: Lesekopf bei Zeit + 38 Samples + LFO * 36 Samples (+-0.75 ms), linear interpoliert (Q8); Rueckkopplung vom
          modulierten Kopf (Modulation waechst mit den Wiederholungen); Speed 0.5 .. 9.9 Hz; Ausgang mono.
  CHODEL: sauberer Kopf bei Zeit + modulierter Kopf bei Zeit + 480 Samples (10 ms) + -LFO * 96 Samples (+-2 ms),
          links +LFO, rechts -LFO; Ausgang je Seite (sauber + moduliert); Rueckkopplung vom sauberen Kopf; Speed 0.1 .. 3 Hz.
  LFO: Dreieck, kubisch gerundet ((3t - t^3)/2) wie beim Phaser.
  Schleife: Tiefpass 1-Pol a = 1/2 (~5.3 kHz) und Hochpass 1-Pol 3/256 (~90 Hz) - zwischen Stock (1.4 kHz) und Digital.
Speicher: Schleife 0x4018a788 (64x128, 1024 B), Setup 0x401904b4, Namen NX2 0x4018fc74, Weiche MD + W2 + SP 0x4018f4b4 (47x47, 376 B).
RAM: Zustand 0x4233c320..0x4233c357 (gecachter Alias; v1 0x4a33c320 ungecacht).
Aufruf: gen_moddelay_113.py <section_3_MAIN_OS.bin der Cycles 1.13> <out.json>
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
from gen_chorusfx import check_cf, DESC, COPY, HELD
import gen_fx4 as fx
import gen_chorus_113 as ch
import gen_phaser_113 as ph
import gen_digidelay_113 as dd
import gen_razer_113 as rz
import gen_delaynotes_113 as dn
import gen_overlay_113 as ovl

M_LOOP, M_SETUP, M_NX, M_MISC = 0x4018A788, 0x401904B4, 0x4018FC74, 0x4018F4B4
M_OV, M_SL = 0x4015C044, 0x4018DBA8                # Anzeige (64x90, 720 B), SLOW + H4-Tabelle (47x47)
M_NP, M_NPS = 0x40172608, 0x40179730              # Popup im Stil der Firmware: Code | Texte (je 47x47, 376 B)
M_FONT = 0x4014AB5C                                # Schrift + Beschriftungen der Anzeige (35x35, 280 B; v3: 0x4014aa34 27x27 zu klein)
SIZE = {M_LOOP: 1024, M_SETUP: 376, M_NX: 376, M_MISC: 376, M_OV: 720, M_SL: 376, M_FONT: 280, M_NP: 376, M_NPS: 376}
ENC_SPEED = 8                                      # DELAY SEND (Regler n -> Eintrag n-2: 8 -> Deskriptor 26)
KEY_SET = 13                                       # SETTINGS (1.13: Hauptbildschirm 0x4001c0e4 Fall 13 -> Loslassen oeffnet
                                                   #   ModelSettingsMenu (+0x9c), langes Halten 533 ms -> Projekt speichern 0x40039570)
CONSUME = 0x400723E0                               # KeyEvent-consume(code): kein Halten/Lang/Loslassen mehr fuer diese Taste
ENC_SKIP = 0x400081E0                              # Encoder-Nachricht fertig (nach lea $20(a7),a7): Sprung mit lea 12(a7),a7
                                                   #   (Ruecksprung + d5 + d0 vom Stack) = Ereignis weder gebaut noch verteilt
MSTATE, MMAGIC = 0x4233C320, 0x4D4F4431           # 'MOD1' ; gecachter Alias von 0x4a33c320 (v1 ungecacht: +5 % / +10 % Last)
PH_, INC, DEP, MODEF, MOD, Y0, YL, YR, DMOD = 20, 24, 28, 32, 36, 40, 44, 48, 52
DMODE, SPEED = 0x404E9B5C, 0x404E9B5B
LMASK, LINE = fx.LMASK, fx.LINE
B_VIB, B_CHO = 3, 2                                # Byte-Werte
VB, CB = 38, 480                                   # Grundversatz VIBDEL / CHODEL (Samples)
DEP_V, DEP_C = 36 * 256, 96 * 256                  # Tiefe in Q8-Samples
SPD_V, SPD_C = (52, 44739), (16, 8948)             # Zuwachs je Frame = S*S*k + b  (0.5..9.9 Hz / 0.1..3.0 Hz)
SCRATCH = ch.SCRATCH
H_HOOK = ch.H_HOOK
NE, EQ, PL, LS, CC, BRA, BSR, HI, LE = 0x6, 0x7, 0xA, 0x3, 0x4, 0x0, 0x1, 0x2, 0xF
NAMES = {0: (b"Digi Send", b"DIGS", b"Digi Time", b"TIME", b"Digi Fdbk", b"FDBK"),
         2: (b"CHODEL Send", b"CHOD", b"CHODEL Time", b"TIME", b"CHODEL Fdbk", b"FDBK"),
         3: (b"VIBDEL Send", b"VIBD", b"VIBDEL Time", b"TIME", b"VIBDEL Fdbk", b"FDBK")}


def build_loop():
    a = A(M_LOOP); w, l = a.w, a.l32
    # v2 (25.10.2026, Pips Lastmessung: Digi 77 %, VIBDEL 82 %, CHODEL 87 % Mittel): LFO nur noch einmal je Block (32 Frames)
    # am Blockende berechnet, dazwischen linear (MOD += DMOD je Frame). Spart ~20 Befehle je Frame.
    a.label('pre')
    w(0x202B, PH_, 0x222B, INC, 0xEB89, 0xD081, 0x2740, PH_)   # Phase += 32 * INC
    w(0x2200); a.bcc(PL, 'tp'); w(0x4681)          # move.l d0,d1 ; bpl tp ; not.l d1
    a.label('tp')
    w(0x0481); l(0x40000000); w(0xE081, 0xEE81)    # subi.l #$40000000,d1 ; asr #8 ; asr #7
    w(0x2401, 0x4C01, 0x2800, 0xE082, 0xEE82)      # d2 = t*t >> 15
    w(0x4C01, 0x2800, 0xE082, 0xEE82)              # d2 = d2*t >> 15   (t^3)
    w(0x2E01, 0xD281, 0xD287, 0x9282, 0xE281)      # d1 = (3t - t^3) >> 1
    w(0x242B, DEP, 0x4C02, 0x1800, 0xE081, 0xEE81) # d1 = d1*DEP >> 15   (mod am Blockende, Q8)
    w(0x2001, 0x90AB, MOD, 0xEA80, 0x2740, DMOD)   # DMOD = (Ende - MOD) >> 5
    a.label('loop')
    # Gleiten wie Digital / Original
    w(0x200C, 0x9084, 0x2E00, 0xE087, 0xEA87); a.bcc(NE, 'add')
    w(0x4A80); a.bcc(EQ, 'nost')
    w(0x2203, 0x0281); l(3); a.bcc(NE, 'nost')
    w(0x7E01, 0x4A80); a.bcc(PL, 'add'); w(0x7EFF)
    a.label('add'); w(0xD887)
    a.label('nost')
    # LFO linear zwischen den Blockenden: MOD += DMOD
    w(0x222B, MOD, 0xD2AB, DMOD, 0x2741, MOD)
    w(0x4AAB, MODEF); a.bcc(NE, 'cho')             # tst.l MODEF(a3) ; bne cho
    # VIBDEL: y = interp((w - cur - VB) << 8 - mod)
    w(0x2003, 0x9084, 0x0480); l(VB); w(0xE188, 0x9081)   # d0 = ((w - cur - VB) << 8) - mod
    a.bcc(BSR, 'ip'); w(0x2200)                    # bsr ip ; move.l d0,d1   (y = Rueckkopplung)
    a.bcc(BRA, 'fb')
    a.label('cho')
    w(0x2003, 0x9084, 0x0280); l(LMASK); w(0xE788, 0x2232, 0x0800, 0x2741, Y0)   # y0 = line[w - cur] -> Y0
    w(0x2003, 0x9084, 0x0480); l(CB); w(0xE188, 0x90AB, MOD)   # d0 = ((w - cur - CB) << 8) - mod
    a.bcc(BSR, 'ip'); w(0x2740, YL)
    w(0x2003, 0x9084, 0x0480); l(CB); w(0xE188, 0xD0AB, MOD)   # d0 = ((w - cur - CB) << 8) + mod
    a.bcc(BSR, 'ip'); w(0x2740, YR)
    w(0x222B, Y0)                                  # move.l Y0(a3),d1   (Rueckkopplung vom sauberen Kopf)
    a.label('fb')
    # Rueckkopplung + Eingang wie Digital: s = sats(x + g*y)
    w(0x2E0D)
    w(0x2001, 0xE080, 0xEE80, 0x4C07, 0x0800)
    w(0x2401, 0x0282); l(0x7FFF)
    w(0x4C07, 0x2800, 0xE082, 0xEE82, 0xD082)
    w(0x2418, 0xE682, 0x2E18, 0xE687, 0xD487)
    w(0xD082, 0x4C80)
    # Tiefpass 1/2: lp = s/2 + lp/2
    w(0xE280, 0x2406, 0xE282, 0xD082, 0x2C00)
    # Hochpass 3/256: h = lp - tief ; q = h>>7 ; tief += q ; h -= q ; q >>= 1 ; tief += q ; h -= q
    w(0x2406, 0x2E0E, 0x9487)
    w(0x2002, 0xEE80, 0xDE80, 0x9480, 0xE280, 0xDE80, 0x9480, 0x2C47)
    w(0x2003, 0xE788, 0x2582, 0x0800)                   # Zeile[w] = h (nur L: beide Lesekoepfe lesen nur L)
    w(0x4AAB, MODEF); a.bcc(NE, 'cout')
    w(0xD281, 0x4C81, 0xD281, 0x4C81, 0x22C1, 0x22C1)   # VIBDEL: out = 4y (L = R)
    a.bcc(BRA, 'next')
    a.label('cout')                                # CHODEL: L = 4*(y0/2 + yL/2), R = 4*(y0/2 + yR/2)
    w(0x202B, Y0, 0xE280)
    w(0x222B, YL, 0xE281, 0xD280, 0xD281, 0x4C81, 0xD281, 0x4C81, 0x22C1)
    w(0x222B, YR, 0xE281, 0xD280, 0xD281, 0x4C81, 0xD281, 0x4C81, 0x22C1)
    a.label('next')
    w(0x5283, 0x0283); l(LMASK)
    w(0x5385); a.bcc(NE, 'loop')
    w(0x2683, 0x2744, 0x0004, 0x2746, 0x000C, 0x274E, 0x0010)
    w(0x4CD7, 0x7CFC, 0x4FEF, 0x002C, 0x4E75)
    # ip: d0 = Position (Q8) -> d0 = linear interpoliert ; veraendert d1, d2, d7
    a.label('ip')
    w(0x2400, 0xE082, 0x0282); l(LMASK); w(0xE78A)   # d2 = ((pos >> 8) & MASK) << 3
    w(0x0280); l(0xFF)                               # d0 = frac
    w(0x2E32, 0x2800, 0x5082, 0x0282); l(LMASK << 3) # s0 = line[i] ; d2 = (i+1) & MASK
    w(0x2432, 0x2800, 0xE282)                        # s1 >> 1
    w(0x2207, 0xE281, 0x9481, 0xE082)                # d = ((s1>>1) - (s0>>1)) >> 8
    w(0x4C00, 0x2800, 0xD482, 0xD487, 0x2002, 0x4E75)   # d*frac ; *2 ; + s0 ; rts
    code = a.done(); check_cf(code, M_LOOP); assert len(code) <= SIZE[M_LOOP], len(code)
    return code


def build_setup(loop_at):
    a = A(M_SETUP); w, l = a.w, a.l32
    a.label('MS')
    w(0x4FEF, 0xFFD4, 0x48D7, 0x7CFC)
    w(0x206F, 0x0038)
    w(0x7F68, 0x0002, 0xE087, 0x4A87); a.bcc(PL, 'p1'); w(0x7E00)          # Fdbk wie Digital
    a.label('p1')
    w(0x0C87); l(127); a.bcc(LE, 'p2'); w(0x7E7F)
    a.label('p2')
    w(0x203C); l(258); w(0x4C00, 0x7800)
    w(0x2007, 0x4C07, 0x0800, 0xE080, 0xEE80)
    w(0x4C07, 0x0800, 0xE080, 0xEE80)
    w(0x2207, 0xDE87, 0xDE81, 0x9E80, 0xE287)
    w(0x2A47)
    w(0x7150); a.orig(fx.DTIME, 6); w(0x760A); a.orig(fx.DTIME + 10, 6)   # Zeit wie die Firmware (Befehle aus dem Image)
    a.orig(fx.DTIME + 20, 6); w(0x4EB9); l(dn.MD)
    a.orig(fx.DTIME + 32, 14)
    w(0x0C80); l(0x3FC00); a.bcc(LS, 'p3'); w(0x203C); l(0x3FC00)
    a.label('p3')
    w(0x0C80); l(32); a.bcc(CC, 'p4'); w(0x7020)
    a.label('p4')
    w(0x2840)
    w(0x47F9); l(MSTATE)
    w(0x202B, 0x0008, 0x0C80); l(MMAGIC); a.bcc(EQ, 'ok')
    w(0x203C); l(MMAGIC); w(0x2740, 0x0008)
    w(0x7000, 0x2680, 0x2740, 0x000C, 0x2740, 0x0010, 0x2740, PH_, 0x2740, MOD)   # w = lp = tief = Phase = LFO = 0
    w(0x200C, 0x2740, 0x0004)                                            # cur = Ziel
    a.label('ok')
    w(0x7000, 0x1039); l(DMODE)                    # moveq #0,d0 ; move.b DMODE,d0
    w(0x7200, 0x1239); l(SPEED)                    # moveq #0,d1 ; move.b SPEED,d1
    w(0x0C81); l(127); a.bcc(LS, 'sok'); w(0x727F)
    a.label('sok')
    w(0x2401, 0x4C01, 0x2800)                      # d2 = S*S
    w(0x0C80); l(B_CHO); a.bcc(EQ, 'cho')
    w(0x7600 | SPD_V[0], 0x4C03, 0x2800, 0x0682); l(SPD_V[1])
    w(0x2742, INC, 0x243C); l(DEP_V); w(0x2742, DEP, 0x42AB, MODEF)
    a.bcc(BRA, 'go')
    a.label('cho')
    w(0x7600 | SPD_C[0], 0x4C03, 0x2800, 0x0682); l(SPD_C[1])
    w(0x2742, INC, 0x243C); l(DEP_C); w(0x2742, DEP, 0x7001, 0x2740, MODEF)
    a.label('go')
    w(0x2613, 0x282B, 0x0004, 0x2C2B, 0x000C, 0x2C6B, 0x0010)
    w(0x7A20, 0x226F, 0x0030, 0x206F, 0x0034)
    w(0x45F9); l(LINE); w(0x4EF9); l(loop_at)
    code = a.done(); check_cf(code, M_SETUP); assert len(code) <= SIZE[M_SETUP], len(code)
    return code, a.lab['MS']


def build_misc(ms_addr, d_addr, h4_addr, ovs_addr):
    """MD (Delay-Weiche), W2 (Schreib-DMA-Weiche), SP (Speed-Geste vor H4)."""
    a = A(M_MISC); w, l = a.w, a.l32
    a.label('MD')
    w(0x41F9); l(DMODE); w(0x7390, 0x4A81); a.bcc(EQ, 'dig')       # Byte 0 -> Digital
    w(0x0C81); l(B_CHO); a.bcc(EQ, 'ms')
    w(0x0C81); l(B_VIB); a.bcc(EQ, 'ms')
    w(0x4EF9); l(fx.STOCK)                                          # 1 und Muell -> Original
    a.label('dig'); w(0x4EF9); l(d_addr)
    a.label('ms'); w(0x4EF9); l(ms_addr)
    a.label('W2')                                                   # Original: DMA normal; sonst obere Haelfte
    w(0x41F9); l(DMODE); w(0x7190, 0x0C80); l(B_VIB); a.bcc(HI, 'wgo')
    w(0x0C80); l(1); a.bcc(EQ, 'wgo')
    w(0x2039); l(0x8000B988); w(0x0080); l(0x40000); w(0x23C0); l(0x8000B988)
    a.label('wgo'); w(0x4EF9); l(fx.WRITE_DMA)
    a.label('SP')                                                   # SETTINGS + DELAY SEND (Encoder 8) -> Speed
    w(0x202A, 0x0004, 0x0C80); l(ENC_SPEED); a.bcc(NE, 'toh')
    w(0x712A, 0x0008); a.bcc(EQ, 'toh')                             # mvs.b 8(a2),d0 ; beq
    w(0x4878, KEY_SET, 0x4EB9); l(HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'toh')  # SETTINGS gehalten?
    w(0x4878, KEY_SET, 0x4EB9); l(CONSUME); w(0x588F)               # consume(SETTINGS): kein Menue beim Loslassen
    w(0x42B9); l(ovl.VARS + ovl.PEND)                               # und kein aufgeschobenes Speichern
    w(0x7000, 0x1039); l(SPEED); w(0x732A, 0x0008)                  # d0 = Speed ; mvs.b 8(a2),d1
    w(0xD081); a.bcc(PL, 's1'); w(0x7000)
    a.label('s1')
    w(0x0C80); l(127); a.bcc(LE, 's2'); w(0x707F)
    a.label('s2')
    w(0x13C0); l(SCRATCH)
    w(0x4878, 0x0001, 0x4879); l(SCRATCH); w(0x4879); l(SPEED)
    w(0x4EB9); l(COPY); w(0x4FEF, 0x000C)
    w(0x7001, 0x7200, 0x1239); l(SPEED); w(0x4EB9); l(ovs_addr)    # Anzeige: OVS(1, Speed)
    w(0x4FEF, 0x000C, 0x4EF9); l(ENC_SKIP)                          # Ereignis ganz verschlucken (kein Popup der Firmware)
    a.label('toh'); w(0x4EF9); l(h4_addr)
    ovl.build_keys(a, ovl.K_DONE)                                   # SETTINGS im Hauptbildschirm (C13A, LS, C13R)
    code = a.done(); check_cf(code, M_MISC); assert len(code) <= SIZE[M_MISC], len(code)
    return code, a.lab


def build_nx(img):
    """NX2: Delay-Namen nach Byte (0 Digi, 1/Muell Original, 2 CHODEL, 3 VIBDEL)."""
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(DESC(26) + 0x2C), rd(DESC(26) + 0x34), rd(DESC(37) + 0x2C), rd(DESC(37) + 0x34), rd(DESC(38) + 0x2C), rd(DESC(38) + 0x34)]
    a = A(M_NX); w, l = a.w, a.l32
    a.label('NX')
    w(0x41F9); l(DMODE); w(0x7190, 0x0C80); l(3); a.bcc(LS, 'z'); w(0x7001)
    a.label('z')
    w(0xE788, 0x2200, 0xD080, 0xD081)              # d0 = Byte*24
    w(0x43F9); l(0); fixr = len(a.b) - 4
    w(0xD3C0)
    w(0x41F9); l(DESC(26) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41F9); l(DESC(37) + 0x2C); w(0x2099, 0x2159, 0x0008)
    w(0x41E8, 0x0038, 0x2099, 0x2159, 0x0008)
    w(0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_NX)
    while len(code) % 4: code += b'\0'
    rows_at = M_NX + len(code); at = rows_at + 4 * 24; strs = b''; pool = {}; ptrs = []
    def put(sv):
        nonlocal strs
        if sv not in pool: pool[sv] = at + len(strs); strs += sv + b'\0'
        return pool[sv]
    for byte in range(4):
        ptrs += orig if byte == 1 else [put(x) for x in NAMES[byte]]
    code += struct.pack('>24I', *ptrs) + strs
    code[fixr:fixr + 4] = struct.pack('>I', rows_at)
    assert len(code) <= SIZE[M_NX], len(code)
    return bytes(code), a.lab['NX']


def build(img):
    loop = build_loop()
    setup, ms = build_setup(M_LOOP)
    nx, nx_addr = build_nx(img)
    D = dd.build(img)
    h4 = ch.M_H4                                    # H4-Einsprung (Label H liegt am Maskenanfang)
    np_, nps, lnp = ovl.build_np(M_NP, M_NPS)
    ov, font, lov = ovl.build(M_OV, M_FONT, lnp['NPD'])
    sl, lsl = ovl.build_slow(M_SL)
    misc, lab = build_misc(ms, D['d'], h4, lov['OVS'])
    return dict(loop=loop, setup=setup, nx=nx, misc=misc, ms=ms, nx_addr=nx_addr, md=lab['MD'], w2=lab['W2'], sp=lab['SP'], h4=h4,
                ov=ov, font=font, np=np_, nps=nps, npd=lnp['NPD'], ovs=lov['OVS'], ovt=lov['OVT'], sl=sl, slow=lsl['SLOW'], table_at=lsl['END'],
                c13a=lab['C13A'], ls=lab['LS'], c13r=lab['C13R'])


def tweak(img):
    M = build(img)
    base = img
    for t0 in (dn.tweak(img)[0], ch.tweak(img)[0], ph.tweak(img)[0], dd.tweak(img)[0], rz.tweak(img)[0]):
        base = dd.apply(base, t0)
    _, popt = ph.phaser_opts()
    Z = rz.build_razer()
    ropt = dict(addr=Z['rz'], row=rz.ROW, str_at=Z['str_at'])
    parts, lab, _ = ch.build(img, phaser=popt, nx=M['nx_addr'], extra_entries=[(15, DMODE, 3, [2], 1)], razer=ropt, h4_xor=True,
                             h4_slow=M['slow'], ent_ext=M['table_at'])
    assert lab['H'] == M['h4']
    slblob = M['sl'] + lab['table']; assert len(slblob) <= SIZE[M_SL], len(slblob)
    own = {M_LOOP: M['loop'], M_SETUP: M['setup'], M_NX: M['nx'], M_MISC: M['misc'], M_OV: M['ov'], M_SL: slblob, M_FONT: M['font'], M_NP: M['np'], M_NPS: M['nps']}
    for va, bb in own.items():
        assert len(bb) <= SIZE[va], (hex(va), len(bb), SIZE[va])
    sw = lambda va, new: {"off": va - BASE, "old": bytes(base[va-BASE:va-BASE+len(new)]).hex(), "new": new.hex()}
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    D = dd.build(img)
    assert base[dd.D_HOOK-BASE:dd.D_HOOK-BASE+6] == jsr(D['d']) and base[dd.W_HOOK-BASE:dd.W_HOOK-BASE+6] == jsr(D['w'])
    assert base[H_HOOK-BASE:H_HOOK-BASE+6] == jsr(M['h4'])
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    w = []
    for va, b in own.items():
        w += [sw(va, b), sprites.redirect_write(va)]
    changed = []
    for va in (ch.M_UI, ch.M_NAMES, ch.M_H4):
        new = parts[va]
        if bytes(base[va - BASE:va - BASE + len(new)]) != new:
            w.append(sw(va, new)); changed.append(f"{va:#x}")
    for va, orig in ((ovl.RENDER_HOOK, ovl.RENDER_ORIG), (ovl.K_HOOK_A, ovl.K_ORIG_A), (ovl.K_HOOK_L, ovl.K_ORIG_L), (ovl.K_HOOK_R, ovl.K_ORIG_R)):
        assert matches(base, va, orig), hex(va)
    w += [sw(dd.D_HOOK, jsr(M['md'])), sw(dd.W_HOOK, jsr(M['w2'])), sw(H_HOOK, jsr(M['sp'])),
          sw(ovl.RENDER_HOOK, jsr(M['ovt'])),
          sw(ovl.K_HOOK_A, jsr(M['c13a']) + bytes.fromhex("4e71")), sw(ovl.K_HOOK_L, jsr(M['ls'])), sw(ovl.K_HOOK_R, jsr(M['c13r']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "mod-delays", "order": 70, "name": "VIBDEL + CHODEL auf dem Delay-Platz (Memory-Man-Idee)",
         "description": ["TRACK + Delay Time: Delay -> Digital -> VIBDEL -> CHODEL (4 Rastungen je Schritt). SETTINGS + DELAY SEND: Speed, mit Anzeige ueber allem.",
                         "SETTINGS lange halten speichert das Projekt erst beim Loslassen (und nur ohne Drehung).",
                         "Feste Tiefe, Wiederholungen leicht abgedunkelt (~5 kHz) und dezent entschlankt (~90 Hz). Erzeugt von gen_moddelay_113.py."],
         "device": "Model:Cycles", "os": "1.13", "section": 3,
         "requires": ["delay-notes", "chorus", "phaser", "digi-delay", "razer"],
         "hooks": [f"{dd.D_HOOK:#x}", f"{dd.W_HOOK:#x}", f"{H_HOOK:#x}", f"{ovl.RENDER_HOOK:#x}", f"{ovl.K_HOOK_A:#x}", f"{ovl.K_HOOK_L:#x}", f"{ovl.K_HOOK_R:#x}"], "changes": changed,
         "settings": ["0x404e9b5c (Werte 0..3)", "0x404e9b5b (Speed)"],
         "memory": [{"va": f"{va:#x}", "size": SIZE[va]} for va in own] + [{"va": f"{MSTATE:#x}", "size": 56, "ram": True}],
         "symbols": {k: f"{M[k]:#x}" for k in ('ms', 'nx_addr', 'md', 'w2', 'sp', 'h4', 'ovs', 'ovt', 'npd', 'slow', 'table_at', 'c13a', 'ls', 'c13r')} | {"loop": f"{M_LOOP:#x}", "R": f"{lab['R']:#x}"},
         "params": {"vb": VB, "cb": CB, "dep_v": DEP_V, "dep_c": DEP_C, "spd_v": SPD_V, "spd_c": SPD_C},
         "writes": w}
    return t, (M, parts, lab)


if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, (M, parts, lab) = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print({k: len(v) for k, v in M.items() if isinstance(v, bytes)}, t["symbols"], "geaendert:", t["changes"])
