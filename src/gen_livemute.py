#!/usr/bin/env python3
"""Tweak 'live-mute' (Model:Cycles OS 1.13): Live-Noten (Pads/Tasten und MIDI-Eingang, sofern sie über die gemeinsame
Live-Noten-Funktion 0x4005894a laufen) werden für gemutete Tracks verworfen. Nur Note-On (Nachricht+0xC == 1);
Note-Off läuft weiter. Haken: erste 6 Bytes von 0x4005894a. Code im freien Sprite-Masken-Bereich 0x401696a0.
"""
import json, struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BEQ, BNE, BASE, matches
MASK, GETM = 0x401696a0, 0x4001263c
ENTRY = MASK
FUNC, RESUME = 0x4005894a, 0x40058950
FUNC_CK = (6, '8d1503d38f264a9b0be0700a53c1e2e61354803cc529f54092a511ae826bca7f')   # Laenge + SHA-256 der ersetzten Originalbefehle

def build():
    """Anfang der Live-Noten-Funktion 0x4005894a (a2 = Nachricht): Note-On fuer einen gemuteten Track verwerfen"""
    from cfasm import asm, done as adone
    a = A(ENTRY)
    asm(a, f'''
            orig    {FUNC:#x},6              ; ersetzte Originalbefehle (aus dem Image)
            moveq   #1,d0
            cmp.l   12(a2),d0                ; Note-On?
            bne     cont
            move.l  (a2),d1                  ; Track
            move.l  d1,-(sp)
            jsr     0x400cf866               ; Singleton
            move.l  d0,-(sp)
            jsr     0x4000eb90               ; -> Kit
            addq.l  #4,sp
            move.l  d0,-(sp)
            jsr     {GETM:#x}                ; Mute(Kit, Track)
            addq.l  #8,sp
            tst.b   d0
            beq     cont
            movea.l (sp)+,a2                 ; Note verwerfen
            rts
    cont:   jmp     {RESUME:#x}
    ''')
    return adone(a)

def tweak(stock):
    code = build()
    assert len(code) <= 280
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    sw = lambda va, new: {"off": va - BASE, "old": stock[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    assert matches(stock, FUNC, FUNC_CK)
    writes = [sw(ENTRY, code), sprites.redirect_write(MASK), sw(FUNC, bytes.fromhex("4ef9") + struct.pack('>I', ENTRY))]
    writes.sort(key=lambda w: w["off"])
    return {"id": "live-mute", "order": 63, "name": "Mute gilt auch für Live-Noten (MIDI-Eingang)",
            "description": ["Note-On für einen gemuteten Track wird verworfen, auch von außen per MIDI (und über die Pads).",
                            f"Code {len(code)} B im Sprite-Maskenbereich {MASK:#x}. Erzeugt von gen_livemute.py."],
            "device": "Model:Cycles", "os": "1.13", "section": 3, "writes": writes}, code

if __name__ == "__main__":
    stock = open(sys.argv[1], 'rb').read()
    t, code = tweak(stock)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("code bytes:", len(code))
