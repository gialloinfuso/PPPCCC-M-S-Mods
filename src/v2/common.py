"""Gemeinsame Konstanten und Helfer der v2-Generatoren (modulare Struktur, Pip 26.10.2026).

Struktur: 00 core (Dienste) | 01..04 unabhaengig (v1-Generatoren) | 05 reverb-fx, 06 delay-fx, 07 strum, 08 load-meter,
09 groove: jeweils nur core. Jede Mod belegt eigene Masken, eigene Haken und genau einen Platz in der Slot-Tabelle des
Cores (Encoder-Gesten). Gemeinsame Daten: Pattern-Kopf-Bytes 40..63 (Core kopiert/loescht sie), VARS (Popup, PEND).
"""
import json, struct, sys, pathlib, hashlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'solo'))
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools'))
from gen_solo import A, BASE, orig_bytes, orig_span   # noqa: E402
import gen_solo                                  # noqa: E402
from gen_chorusfx import check_cf                # noqa: E402
import sprites                                   # noqa: E402

# ---- Bedingungen fuer A.bcc
BRA, BSR, HI, LS, CC, CS, NE, EQ, PL, MI, GE, LT, GT, LE = 0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0xA, 0xB, 0xC, 0xD, 0xE, 0xF

# ---- Firmware 1.13
HELD, CONSUME, COPY = 0x4007FAF4, 0x400723E0, 0x40044B88
ENC_SKIP = 0x400081E0                 # Encoder-Nachricht verwerfen (Sprung mit lea 12(a7),a7 auf Haken-Ebene)
H_HOOK, H_ORIG = 0x400081B8, (6, '9bb3f43c614c29728d69125a337d8aa2786eb191967f271dfb2a735504ba1f66')   # Laenge + SHA-256 der Originalbefehle (mvs.b 8(a2),d1 ; move.l d1,-(a7))
CUR_PAT = 0x40A7887C                  # *(...) = laufendes Pattern B
HDR = 0x77B2                          # Pattern-Kopf in B (64 Byte)
SEL_A, SEL_B, SEL_C = 0x400CF866, 0x4000EB90, 0x40012412   # ausgewaehlter Track = C(B(A()))
DESC = lambda k: 0x4010DCE0 + 0x38 * k          # Parameter-Deskriptor k: +0x2c Name, +0x34 Kurzname
TIMER = 0xFC07000C                    # DMA-Zeitgeber 0, 135.168 MHz
KEY_FUNC, KEY_TRACK, KEY_MACH, KEY_SET = 1, 2, 5, 13
ENC_SHAPE, ENC_DSEND, ENC_RSEND, ENC_SWING, ENC_RSIZE, ENC_DTIME = 5, 8, 9, 12, 14, 15

# ---- Pattern-Kopf: Belegung (Byte-Offset im 64-Byte-Kopf). Core kopiert 40..63 beim Laden und loescht sie fuer neue Patterns.
P_HUM_T, P_HUM_V = 40, 46             # groove: Humanize Zeit / Velocity, Track 1..6
P_RFX, P_DFX, P_DSPD, P_GROOVE, P_STRUM = 52, 53, 54, 55, 56
P_FIRST, P_LAST = 40, 63
P_SIG, SIG = 60, (0x5043, 0x7632)       # Kennung 'PCv2' in 60..63 (Core)

# ---- Core: RAM und Tabellen
VARS = 0x4A33C380                     # Popup + Tasten (ungecacht, UI und Audio)
V_MAGIC, V_KIND, V_VAL, V_DL, V_VC, V_L1, V_L2, V_FN, V_PEND, V_MPEND = 0, 4, 8, 12, 16, 20, 24, 28, 32, 36
ACC = 0x4A33C3C0                      # SLOW: +0 Summe, +4 Ziel, +8 Zeit
CTRL_MODE = 0x404E9B5D                # global (Einstellungsblock, beim Ausschalten gespeichert): CONTROL ALL
CTRL_ABS = 0x5A                       # == CTRL_ABS: absolut; alles andere (0 nach Reset, v1-Reste 1..4): relativ = Firmware
NSLOT = 8
SLOT = {'reverb-fx': 0, 'delay-fx': 1, 'strum': 2, 'load-meter': 3, 'groove': 4, 'control-mode': 5, 'trig-select': 6, 'track-filter': 7}
NKSLOT = 2                            # SETTINGS-Tasten-Slots (Druecken / Loslassen im Hauptbildschirm)
KSLOT = {'control-mode': 0}
NSSLOT = 4                            # Sound-Slots: Handler (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern) fuer eigene Parameter
SSLOT = {'track-filter': 0, 'lfo-amount': 1}
K_EXT0, K_EXT1 = 23, 32               # k 23..32: Parameter ohne Platz in der Firmware (Core: p-locks, LFO-/Velocity-Ziel im Sound)
CM_SU, CM_SCR = 0x4A33C3A8, 0x4A33C3A9   # control-mode: SETTINGS benutzt (Druecken..Loslassen), Byte fuer COPY
# Popup-Arten fuer OVS
OV_HIDE, OV_NUM, OV_TEXT, OV_CUSTOM = 0, 1, 2, 3

jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
jmp = lambda t: bytes.fromhex("4ef9") + struct.pack('>I', t)


def apply(img, t):
    """Patch (Entwicklungsformat mit 'old') auf ein Image anwenden, 'old' pruefen."""
    b = bytearray(img)
    for x in t['writes']:
        o = bytes.fromhex(x['old']); n = bytes.fromhex(x['new'])
        assert b[x['off']:x['off'] + len(o)] == o, (t['id'], hex(x['off'] + BASE))
        b[x['off']:x['off'] + len(n)] = n
    return bytes(b)


class Writes:
    """Sammelt Schreibstellen gegen ein Basis-Image (old = Bytes der Basis)."""
    def __init__(s, base):
        s.base, s.w, s.masks = base, [], []
    def put(s, va, new):
        s.w.append({"off": va - BASE, "old": bytes(s.base[va - BASE:va - BASE + len(new)]).hex(), "new": bytes(new).hex()})
    def mask(s, va, blob, size):
        assert len(blob) <= size, (hex(va), len(blob), size)
        assert sprites.MASKS[va][0] == size, hex(va)
        s.put(va, blob); s.w.append(sprites.redirect_write(va)); s.masks.append({"va": f"{va:#x}", "size": size})
    def hook(s, va, ck, new):
        """ck = (Laenge, SHA-256-Hex) der erwarteten Original-Bytes (keine Original-Bytes im Quelltext), oder Bytes, die nur
        aus einer Adresse gebaut sind (Vtable-Eintrag, jsr <Funktion>)."""
        if isinstance(ck, tuple):
            n, h = ck
            ok = hashlib.sha256(bytes(s.base[va - BASE:va - BASE + n])).hexdigest() == h
        else:
            ok = bytes(s.base[va - BASE:va - BASE + len(ck)]) == ck
        assert ok, f"Haken {va:#x} nicht im Originalzustand"
        s.put(va, new)
    def sorted(s):
        return sorted(s.w, key=lambda x: x["off"])


def patch(pid, order, name, desc, W, **kw):
    t = {"id": pid, "order": order, "name": name, "description": desc, "device": "Model:Cycles", "os": "1.13", "section": 3}
    t.update(kw)
    mem = list(W.masks) + kw.get('memory', [])
    t['memory'] = mem
    t['writes'] = W.sorted()
    return t


def annotate(t):
    """Dev-Format: jeder Write bekommt 'orig' = [[at, Quell-Offset, n], ...] fuer die Bytes, die Original-Bytes der Firmware
    sind (gen_solo.ORIGS). Der Export ersetzt sie durch Platzhalter."""
    spans = sorted(set(gen_solo.ORIGS))
    for w in t['writes']:
        va = w['off'] + BASE; new = bytes.fromhex(w['new']); got = []
        for tv, sv, n in spans:
            if va <= tv and tv + n <= va + len(new) and new[tv - va:tv - va + n] == orig_bytes(sv, n):
                got.append([tv - va, sv - BASE, n])
        got = sorted({tuple(g) for g in got})
        for a, b in zip(got, got[1:]):
            assert a[0] + a[2] <= b[0], (t['id'], hex(va), a, b)
        if got: w['orig'] = [list(g) for g in got]
        elif 'orig' in w: del w['orig']
    return t


def stock():
    return open(ROOT / 'out' / 'section_3_MAIN_OS.bin', 'rb').read()


def save(t, path):
    pathlib.Path(path).write_text(json.dumps(t, indent=1) + "\n")
