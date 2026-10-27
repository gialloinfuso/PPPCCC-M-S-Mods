#!/usr/bin/env python3
"""Erzeugt den Tweak 'mute-solo' (Model:Cycles OS 1.13) ohne m68k-Assembler: Maschinencode wird hier von Hand kodiert.

Idee: Im eingerasteten Mute-Modus (latching-mute, Flag 0x401487ed) wird bei FUNC (Taste 1) gehalten + Track-Taste
nicht mehr getoggelt, sondern gesolot. Haken: der Aufruf jsr 0x40013904 (Mute toggeln) bei 0x40023550 in der
Mute-Ansicht (QuickMuteMenuView). Argumente liegen schon auf dem Stack: (kit, track, 1).
Benutzte OS-Funktionen: 0x4001263c(kit,track)=Mute lesen, 0x4001381c(kit,track,wert,1)=Mute setzen,
0x4007faf4(code)=Taste gehalten.
"""
import json, struct, sys, pathlib, hashlib
BASE = 0x40000400
MASK = 0x40167c50            # freigegebenes 35x35-Sprite-Maske (280 B), constante 0x400b211e
GETM, SETM, KEYH, TOGGLE = 0x4001263c, 0x4001381c, 0x4007faf4, 0x40013904
LATCH = 0x401487ed
ENTRY = MASK
SAVED = MASK + 0x108         # 6 Bytes: gesicherter Mute-Zustand
SOLOF = MASK + 0x10E         # Byte: 0 = kein Solo, sonst Track+1

# ---- Original-Bytes der Firmware (an Haken verschobene Befehle, uebernommene Zeiger): stehen NIE im Quelltext und NIE in
# den oeffentlichen Patches. Der Generator kopiert sie aus dem Image (ORIG_IMAGE oder out/section_3_MAIN_OS.bin) und merkt
# sich die Stelle in ORIGS (Ziel-VA, Quell-VA, Laenge). Der Export ersetzt sie durch Platzhalter + SHA-256; das Build-Tool
# kopiert sie beim Bauen aus der Firmware-Datei des Nutzers.
ORIGS = []
ORIG_IMAGE = None


def orig_image():
    global ORIG_IMAGE
    if ORIG_IMAGE is None:
        ORIG_IMAGE = (pathlib.Path(__file__).resolve().parents[1] / 'out' / 'section_3_MAIN_OS.bin').read_bytes()
    return ORIG_IMAGE


def orig_bytes(va, n):
    return orig_image()[va - BASE:va - BASE + n]


def orig_span(target_va, va, n):
    """Bytes target_va..+n eines Patches sind die Original-Bytes va..+n (z. B. ein aus dem Image gelesener Zeiger)."""
    ORIGS.append((target_va, va, n))
    return orig_bytes(va, n)


def matches(img, va, ck):
    """Haken-Pruefung ohne Original-Bytes im Quelltext: ck = (Laenge, SHA-256-Hex) der erwarteten Bytes ab va in img."""
    n, h = ck
    return hashlib.sha256(bytes(img[va - BASE:va - BASE + n])).hexdigest() == h


class A:
    def __init__(s, org): s.org, s.b, s.lab, s.fix = org, bytearray(), {}, []
    def orig(s, va, n):
        """n Original-Bytes ab va hier einfuegen (verschobene Befehle eines Hakens)."""
        s.b += orig_span(s.org + len(s.b), va, n)
    def w(s, *words):
        for x in words: s.b += struct.pack('>H', x)
    def l32(s, v): s.b += struct.pack('>I', v)
    def label(s, n): s.lab[n] = s.org + len(s.b)
    def bcc(s, op, n):            # Bcc.W (16-Bit-Verschiebung)
        s.w(0x6000 | (op << 8)); s.fix.append((len(s.b), n)); s.w(0)
    def done(s):
        for pos, n in s.fix:
            disp = s.lab[n] - (s.org + pos)       # relativ zur Adresse des Erweiterungsworts
            assert -32768 <= disp < 32768
            s.b[pos:pos+2] = struct.pack('>h', disp)
        return bytes(s.b)

BRA, BNE, BEQ, BLT = 0x0, 0x6, 0x7, 0xD

def build():
    a = A(ENTRY)
    # -- Solo nur im eingerasteten Mute-Modus und bei gehaltener FUNC-Taste
    a.w(0x4A39); a.l32(LATCH)                       # tst.b LATCH
    a.bcc(BEQ, 'orig')
    a.w(0x4878, 0x0001); a.w(0x4EB9); a.l32(KEYH)    # pea 1 ; jsr KEYH
    a.w(0x588F)                                      # addq.l #4,a7
    a.w(0x4A80)                                      # tst.l d0
    a.bcc(BEQ, 'orig')
    # -- Solo
    a.w(0x4FEF, 0xFFF0); a.w(0x48D7, 0x041C)         # lea -16(a7),a7 ; movem.l d2-d4/a2,(a7)
    a.w(0x246F, 0x0014)                              # movea.l 20(a7),a2   (kit)
    a.w(0x242F, 0x0018)                              # move.l  24(a7),d2   (track)
    a.w(0x2052, 0x2F0A, 0x2068, 0x0028, 0x4E90, 0x588F, 0x4A80)  # movea.l (a2),a0; push a2; movea.l 40(a0),a0; jsr (a0); addq; tst
    a.bcc(BEQ, 'done')                               # Kit nicht bereit
    a.w(0x7005, 0xB082)                              # moveq #5,d0 ; cmp.l d2,d0
    a.w(0x6500); a.fix.append((len(a.b), 'done')); a.w(0)   # bcs done (Track > 5)
    a.w(0x7000, 0x1039); a.l32(SOLOF)                # moveq #0,d0 ; move.b SOLOF,d0
    a.w(0x2202, 0x5281, 0xB280)                      # move.l d2,d1 ; addq.l #1,d1 ; cmp.l d0,d1
    a.bcc(BEQ, 'restore')
    a.w(0x4A80)                                      # tst.l d0
    a.bcc(BNE, 'setall')                             # schon Solo auf anderem Track: Sicherung behalten
    a.w(0x7600)                                      # moveq #0,d3
    a.label('save')
    a.w(0x2F03, 0x2F0A, 0x4EB9); a.l32(GETM)         # push d3; push a2; jsr GETM
    a.w(0x508F, 0x7180)                              # addq.l #8,a7 ; mvz.b d0,d0
    a.w(0x41F9); a.l32(SAVED)                        # lea SAVED,a0
    a.w(0x1180, 0x3800)                              # move.b d0,(0,a0,d3.l)
    a.w(0x5283, 0x7006, 0xB680)                      # addq.l #1,d3 ; moveq #6,d0 ; cmp.l d0,d3
    a.bcc(BLT, 'save')
    a.label('setall')
    a.w(0x7600)                                      # moveq #0,d3
    a.label('setl')
    a.w(0x7801, 0xB682)                              # moveq #1,d4 ; cmp.l d2,d3
    a.bcc(BNE, 'sv')
    a.w(0x7800)                                      # moveq #0,d4  (gewählter Track bleibt hörbar)
    a.label('sv')
    a.w(0x4878, 0x0001, 0x2F04, 0x2F03, 0x2F0A, 0x4EB9); a.l32(SETM)
    a.w(0x4FEF, 0x0010)                              # lea 16(a7),a7
    a.w(0x5283, 0x7006, 0xB680)
    a.bcc(BLT, 'setl')
    a.w(0x2002, 0x5280, 0x13C0); a.l32(SOLOF)        # d0=track+1 ; move.b d0,SOLOF
    a.bcc(BRA, 'done')
    a.label('restore')
    a.w(0x7600)                                      # moveq #0,d3
    a.label('rl')
    a.w(0x41F9); a.l32(SAVED)                        # lea SAVED,a0
    a.w(0x7800, 0x1830, 0x3800)                      # moveq #0,d4 ; move.b (0,a0,d3.l),d4
    a.w(0x4878, 0x0001, 0x2F04, 0x2F03, 0x2F0A, 0x4EB9); a.l32(SETM)
    a.w(0x4FEF, 0x0010)
    a.w(0x5283, 0x7006, 0xB680)
    a.bcc(BLT, 'rl')
    a.w(0x4239); a.l32(SOLOF)                        # clr.b SOLOF
    a.label('done')
    a.w(0x4CD7, 0x041C, 0x4FEF, 0x0010, 0x4E75)      # movem.l (a7),d2-d4/a2 ; lea 16(a7),a7 ; rts
    a.label('orig')
    a.w(0x4239); a.l32(SOLOF)                        # normaler Mute-Druck beendet ein Solo
    a.w(0x4EF9); a.l32(TOGGLE)                       # jmp TOGGLE (Argumente liegen noch auf dem Stack)
    return a.done(), a.lab

def tweak(stock):
    code, lab = build()
    assert len(code) <= 0x108, len(code)
    sw = lambda va, new: {"off": va - BASE, "old": stock[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    hook_old = stock[0x40023550-BASE:0x40023550-BASE+6]
    assert matches(stock, 0x40023550, (6, '547f231bd41f965dbbe4e0fdec93c267ac2849729718f9e81e1a18d7f7513740')), "Haken 0x40023550 nicht im Originalzustand (jsr Mute toggeln)"
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    writes = [sw(ENTRY, code), sw(SAVED, bytes(8)), sprites.redirect_write(MASK),
              sw(0x40023550, bytes.fromhex("4eb9") + struct.pack('>I', ENTRY))]
    writes.sort(key=lambda w: w["off"])
    return {"id": "mute-solo", "order": 62, "name": "Mute-Modus mit Solo",
            "description": ["Im eingerasteten Mute-Modus (latching-mute): FUNC halten + Track-Taste = Solo; nochmal = vorheriger Mute-Zustand zurück.",
                            f"Code {len(code)} B im freigegebenen Sprite-Maske {MASK:#x}. Erzeugt von gen_solo.py."],
            "device": "Model:Cycles", "os": "1.13", "section": 3,
            "requires": ["latching-mute"], "conflicts": ["model-tg", "model-tg-st"],
            "symbols": {"solo_entry": f"{ENTRY:#x}", "saved": f"{SAVED:#x}", "solo_flag": f"{SOLOF:#x}"},
            "writes": writes}, code

if __name__ == "__main__":
    stock = open(sys.argv[1], 'rb').read()
    t, code = tweak(stock)
    out = pathlib.Path(sys.argv[2]); out.write_text(json.dumps(t, indent=1) + "\n")
    print("code bytes:", len(code), "->", out)
