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
    a = A(ENTRY)
    a.orig(FUNC, 6)                                  # ersetzte Originalbefehle (aus dem Image)
    a.w(0x7001, 0xB0AA, 0x000C)                      # moveq #1,d0 ; cmp.l 12(a2),d0   (Note-On?)
    a.bcc(BNE, 'cont')
    a.w(0x2212, 0x2F01)                              # move.l (a2),d1 (Track) ; push
    a.w(0x4EB9); a.l32(0x400CF866)                   # jsr singleton
    a.w(0x2F00, 0x4EB9); a.l32(0x4000EB90)           # push ; jsr -> Kit
    a.w(0x588F, 0x2F00, 0x4EB9); a.l32(GETM)         # pop ; push Kit ; jsr getMute(kit, track)
    a.w(0x508F, 0x4A00)                              # addq.l #8,a7 ; tst.b d0
    a.bcc(BEQ, 'cont')
    a.w(0x245F, 0x4E75)                              # movea.l (a7)+,a2 ; rts   (Note verwerfen)
    a.label('cont')
    a.w(0x4EF9); a.l32(RESUME)                       # jmp 0x40058950
    return a.done()

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
