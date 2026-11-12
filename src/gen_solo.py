#!/usr/bin/env python3
"""Erzeugt den Tweak 'mute-solo' (Model:Cycles OS 1.13) ohne m68k-Assembler: Maschinencode wird hier von Hand kodiert.

Idee: Im eingerasteten Mute-Modus (latching-mute, Flag 0x401487ed) wird bei FUNC (Taste 1) gehalten + Track-Taste
nicht mehr getoggelt, sondern gesolot. Haken: der Aufruf jsr 0x40013904 (Mute toggeln) bei 0x40023550 in der
Mute-Ansicht (QuickMuteMenuView). Argumente liegen schon auf dem Stack: (kit, track, 1).
Benutzte OS-Funktionen: 0x4001263c(kit,track)=Mute lesen, 0x4001381c(kit,track,wert,1)=Mute setzen,
0x4007faf4(code)=Taste gehalten.
"""
import json, struct, sys, pathlib, hashlib
sys.path.insert(1, str(pathlib.Path(__file__).resolve().parents[1] / 'v2'))   # cfasm (lesbarer Assembler, 2.3)
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
    """Solo in der Mute-Ansicht (statt jsr TOGGLE bei 0x40023550; Stapel: kit, track, 1)"""
    from cfasm import asm, done as adone
    a = A(ENTRY)
    asm(a, f'''
    ; Solo nur im eingerasteten Mute-Modus und bei gehaltener FUNC-Taste
            tst.b   {LATCH:#x}
            beq     orig
            pea     1.w
            jsr     {KEYH:#x}                ; FUNC gehalten?
            addq.l  #4,sp
            tst.l   d0
            beq     orig
    ; Solo
            lea     -16(sp),sp
            movem.l d2-d4/a2,(sp)
            movea.l 20(sp),a2                ; Kit
            move.l  24(sp),d2                ; Track
            movea.l (a2),a0
            move.l  a2,-(sp)
            movea.l 40(a0),a0
            jsr     (a0)
            addq.l  #4,sp
            tst.l   d0
            beq     done                     ; Kit nicht bereit
            moveq   #5,d0
            cmp.l   d2,d0
            bcs     done                     ; Track > 5
            moveq   #0,d0
            move.b  {SOLOF:#x},d0
            move.l  d2,d1
            addq.l  #1,d1
            cmp.l   d0,d1
            beq     restore                  ; derselbe Track nochmal: Solo aus
            tst.l   d0
            bne     setall                   ; schon Solo auf anderem Track: Sicherung behalten
            moveq   #0,d3
    save:   move.l  d3,-(sp)                 ; Mute-Zustand aller Tracks sichern
            move.l  a2,-(sp)
            jsr     {GETM:#x}
            addq.l  #8,sp
            mvz.b   d0,d0
            lea     {SAVED:#x},a0
            move.b  d0,0(a0,d3.l)
            addq.l  #1,d3
            moveq   #6,d0
            cmp.l   d0,d3
            blt     save
    setall: moveq   #0,d3
    setl:   moveq   #1,d4                    ; alle muten ...
            cmp.l   d2,d3
            bne     sv
            moveq   #0,d4                    ; ... ausser dem gewaehlten Track
    sv:     pea     1.w
            move.l  d4,-(sp)
            move.l  d3,-(sp)
            move.l  a2,-(sp)
            jsr     {SETM:#x}
            lea     16(sp),sp
            addq.l  #1,d3
            moveq   #6,d0
            cmp.l   d0,d3
            blt     setl
            move.l  d2,d0
            addq.l  #1,d0
            move.b  d0,{SOLOF:#x}            ; Solo = Track + 1
            bra     done
    restore: moveq  #0,d3                    ; gesicherten Mute-Zustand zurueck
    rl:     lea     {SAVED:#x},a0
            moveq   #0,d4
            move.b  0(a0,d3.l),d4
            pea     1.w
            move.l  d4,-(sp)
            move.l  d3,-(sp)
            move.l  a2,-(sp)
            jsr     {SETM:#x}
            lea     16(sp),sp
            addq.l  #1,d3
            moveq   #6,d0
            cmp.l   d0,d3
            blt     rl
            clr.b   {SOLOF:#x}
    done:   movem.l (sp),d2-d4/a2
            lea     16(sp),sp
            rts
    orig:   clr.b   {SOLOF:#x}               ; normaler Mute-Druck beendet ein Solo
            jmp     {TOGGLE:#x}              ; Argumente liegen noch auf dem Stapel
    ''')
    return adone(a), a.lab

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
