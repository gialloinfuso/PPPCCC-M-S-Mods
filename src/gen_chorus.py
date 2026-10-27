#!/usr/bin/env python3
"""Tweak 'chorus' (Modded Cycles OS 2.0 / Model:Cycles OS 1.13): mono-Chorus ersetzt den Delay-Effekt (Prototyp).

Der Mixer ruft das Delay (OS 2.0 ueber den Wrapper 0x401b71b0, der am Ende 'jmp 0x40057488' ausfuehrt) so auf:\n  (out=0x8000ba90, in=0x8000b990, params)
  in/out: 32 Frames, interleaved Stereo (L,R je 32 Bit), params: 8.8-Woerter  +0 = Delay Time, +2 = Delay Fdbk.
Der Chorus ersetzt dieses jsr durch jsr CHORUS (gleiche Argumente):
  * Eingang mono: x = (L+R)/2, Ringpuffer 2048 Longs (43 ms) bei 0x4a600000 (+16), Zustand (w, Phase) bei +0 / +4.
  * LFO: Dreieck, Speed = Delay Time (0..127): f = 0.1 .. 6.4 Hz (Phasenzuwachs 8948 + 4474*S pro Sample, 32 Bit).
  * Verzoegerung: 20 ms +- Depth*0.1 ms (Depth = Delay Fdbk, 0..127, bis +-13 ms), lineare Interpolation.
  * Ausgabe: Stereo, der rechte Abgriff laeuft mit gegenlaeufigem LFO (nur Wet, der Dry-Anteil liegt schon im Mix).
Speicher: die Delay-Zeile (0x4a400000, 8 Byte pro Frame) wird auf 0x40000 Frames (2 MB) verkuerzt, damit
0x4a600000..0x4a7fffff frei ist (Maske 0x7ffff -> 0x3ffff an 3 Stellen, Maximalzeit 0x5dc00 -> 0x3fc00).
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE
MASK = 0x40166760                    # freies 35x35-Sprite-Maske (280 B), Konstante 0x400b272e
CALL = 0x401B721C                    # OS 2.0: 'jmp 0x40057488' im Leerlauf-Wrapper 0x401b71b0 (Mixer ruft den Wrapper)
DELAY = 0x40057488
STATE = 0x4A600000                   # +0 w, +4 Phase, +16 Ringpuffer
RING_MASK = 0x7FF
BASE_Q16 = 960 << 16                 # mittlere Verzoegerung (20 ms)
INC0, INCS = 8948, 1761              # Phasenzuwachs: 8948 + 1761*S   (S = 0..127): 0.1 .. 2.6 Hz
DSC = 10                             # Swing in 1/65536 Samples: tri16 * D * 10 (bis +-13 ms)
BNE, BEQ, BPL, BRA = 0x6, 0x7, 0xA, 0x0

def build():
    a = A(MASK)
    w, l = a.w, a.l32
    w(0x4FEF, 0xFFDC)                       # lea -36(a7),a7
    w(0x48D7, 0x1CFC)                       # movem.l d2-d7/a2-a4,(a7)
    w(0x206F, 0x0030)                       # movea.l 48(a7),a0     params
    w(0x71D0)                               # mvz.w (a0),d0         Delay Time (8.8)
    w(0xE088)                               # lsr.l #8,d0           S
    w(0x73E8, 0x0002)                       # mvz.w 2(a0),d1        Delay Fdbk (8.8)
    w(0xE089)                               # lsr.l #8,d1           D
    w(0x283C); l(INCS)                      # move.l #INCS,d4
    w(0x4C00, 0x4800)                       # muls.l d0,d4          S*INCS
    w(0x0684); l(INC0)                      # addi.l #INC0,d4       Phasenzuwachs
    w(0x7C00 | DSC)                         # moveq #DSC,d6
    w(0x4C06, 0x1800)                       # muls.l d6,d1          D*DSC
    w(0x45F9); l(STATE)                     # lea STATE,a2
    w(0x2412)                               # move.l (a2),d2        w
    w(0x262A, 0x0004)                       # move.l 4(a2),d3       Phase
    w(0x47EA, 0x0010)                       # lea 16(a2),a3         Ring
    w(0x206F, 0x002C)                       # movea.l 44(a7),a0     in
    w(0x226F, 0x0028)                       # movea.l 40(a7),a1     out
    w(0x7A20)                               # moveq #32,d5
    a.label('loop')
    w(0x2C18)                               # move.l (a0)+,d6       L
    w(0xE486)                               # asr.l #2,d6
    w(0x2E18)                               # move.l (a0)+,d7       R
    w(0xE487)                               # asr.l #2,d7
    w(0xDC87)                               # add.l d7,d6           (L+R)>>2
    w(0x2786, 0x2C00)                       # move.l d6,0(a3,d2.l*4)
    w(0xD684)                               # add.l d4,d3           Phase += Zuwachs
    w(0x2C03)                               # move.l d3,d6
    a.bcc(BPL, 'pos')                       # bpl.w
    w(0x4686)                               # not.l d6
    a.label('pos')
    w(0x0486); l(0x40000000)                # subi.l #$40000000,d6  Dreieck +-2^30
    w(0xEE86, 0xE086)                       # asr.l #7,d6 ; asr.l #8,d6   -> +-32768
    # Dreieck -> sinusaehnlich: y = (3t - t^3)/2 (Q15, Steigung 0 an den Umkehrpunkten)
    w(0x2E06)                               # move.l d6,d7
    w(0x4C07, 0x7800)                       # muls.l d7,d7          t^2
    w(0xEE87, 0xE087)                       # asr.l #7,d7 ; asr.l #8,d7
    w(0x4C06, 0x7800)                       # muls.l d6,d7          t^3 (Q30)
    w(0xEE87, 0xE087)                       # asr.l #7,d7 ; asr.l #8,d7
    w(0x2006)                               # move.l d6,d0
    w(0xDC86)                               # add.l d6,d6           2t
    w(0xDC80)                               # add.l d0,d6           3t
    w(0x9C87)                               # sub.l d7,d6           3t - t^3
    w(0xE286)                               # asr.l #1,d6
    w(0x4C01, 0x6800)                       # muls.l d1,d6          Swing (Q16 Samples)
    w(0x2846)                               # movea.l d6,a4         Swing merken
    w(0x2E02)                               # move.l d2,d7
    w(0x7010)                               # moveq #16,d0
    w(0xE1AF)                               # lsl.l d0,d7           w<<16
    w(0x9E86)                               # sub.l d6,d7           links:  - Swing
    w(0x0487); l(BASE_Q16)                  # subi.l #BASE_Q16,d7
    a.bcc(1, 'tap')                         # bsr.w tap
    w(0x22C6)                               # move.l d6,(a1)+       L
    w(0x2E02)                               # move.l d2,d7
    w(0x7010)                               # moveq #16,d0
    w(0xE1AF)                               # lsl.l d0,d7
    w(0x2C0C)                               # move.l a4,d6
    w(0xDE86)                               # add.l d6,d7           rechts: + Swing (LFO gegenlaeufig)
    w(0x0487); l(BASE_Q16)                  # subi.l #BASE_Q16,d7
    a.bcc(1, 'tap')                         # bsr.w tap
    w(0x22C6)                               # move.l d6,(a1)+       R
    w(0x5282)                               # addq.l #1,d2
    w(0x0282); l(RING_MASK)                 # andi.l #RING_MASK,d2
    w(0x5385)                               # subq.l #1,d5
    a.bcc(BNE, 'loop')
    w(0x2482)                               # move.l d2,(a2)
    w(0x2543, 0x0004)                       # move.l d3,4(a2)
    w(0x4CD7, 0x1CFC)                       # movem.l (a7),d2-d7/a2-a4
    w(0x4FEF, 0x0024)                       # lea 36(a7),a7
    w(0x4E75)                               # rts
    a.label('tap')                          # d7 = Leseposition Q16 (beliebig, wird maskiert) -> d6 = Ausgabe
    w(0x0287); l((RING_MASK + 1 << 16) - 1) # andi.l #mask,d7
    w(0x2C07)                               # move.l d7,d6
    w(0xE0AE)                               # lsr.l d0,d6           Index (d0 = 16)
    w(0xE28F)                               # lsr.l #1,d7
    w(0x0287); l(0x7FFF)                    # andi.l #$7fff,d7      Bruch (15 Bit)
    w(0x2033, 0x6C00)                       # move.l 0(a3,d6.l*4),d0  s0
    w(0x5286)                               # addq.l #1,d6
    w(0x0286); l(RING_MASK)                 # andi.l #RING_MASK,d6
    w(0x2C33, 0x6C00)                       # move.l 0(a3,d6.l*4),d6  s1
    w(0x9C80)                               # sub.l d0,d6           s1-s0
    w(0xEE86, 0xE086)                       # asr.l #7,d6 ; asr.l #8,d6
    w(0x4C07, 0x6800)                       # muls.l d7,d6
    w(0xDC80)                               # add.l d0,d6           s0 + Delta
    w(0xDC86, 0x4C86)                       # add.l d6,d6 ; sats.l d6   x2
    w(0xDC86, 0x4C86)                       # add.l d6,d6 ; sats.l d6   x2 (+6 dB Wet-Pegel)
    w(0x4E75)                               # rts
    code = a.done()
    assert len(code) <= 280, len(code)
    return code

# 3 Konstanten der Delay-Zeile: Schreib- und Lesemaske, Maximalzeit
PATCH_CONST = [(0x4005740A, 0x7FFFF, 0x3FFFF), (0x40058212, 0x7FFFF, 0x3FFFF), (0x40058218, 0x7FFFF, 0x3FFFF),
               (0x400581CE, 0x5DC00, 0x3FC00), (0x400581D6, 0x5DC00, 0x3FC00)]

def tweak(img):
    sw = lambda va, new: {"off": va - BASE, "old": img[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    code = build()
    assert img[CALL-BASE:CALL-BASE+6] == bytes.fromhex("4ef9") + struct.pack('>I', DELAY)
    w = [sw(MASK, code), sprites.redirect_write(MASK), sw(CALL, bytes.fromhex("4ef9") + struct.pack('>I', MASK))]
    for va, old, new in PATCH_CONST:
        assert img[va-BASE:va-BASE+4] == struct.pack('>I', old), hex(va)
        w.append(sw(va, struct.pack('>I', new)))
    w.sort(key=lambda x: x["off"])
    return {"id": "chorus", "order": 66, "name": "Stereo-Chorus statt Delay (Prototyp)",
            "description": ["Ersetzt den Delay-Effekt durch einen Stereo-Chorus (Mono-Eingang): Delay Time = Speed, Delay Fdbk = Depth.",
                            "Erzeugt von gen_chorus.py."],
            "device": "Model:Cycles", "os": "2.0", "section": 3, "writes": w}, code

if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, code = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("Code", len(code), "Bytes")
    if len(sys.argv) > 3:
        out = bytearray(img)
        for x in t["writes"]:
            o = bytes.fromhex(x["old"]); assert out[x["off"]:x["off"]+len(o)] == o
            out[x["off"]:x["off"]+len(o)] = bytes.fromhex(x["new"])
        pathlib.Path(sys.argv[3]).write_bytes(bytes(out))
