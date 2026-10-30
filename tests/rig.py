"""Gemeinsamer Pruefstand fuer die v2-Tests: Images (Stock, v1 komplett, v2 komplett / Teilmengen), Unicorn mit allen
benoetigten Bereichen, Stubs (HELD, CONSUME, COPY, new/delete), Aufruf von Funktionen und Encoder-Ereignissen ueber den
echten Core-Verteiler (Haken 0x400081b8), Pattern-Kopf im Emulator (CUR_PAT -> eigener B-Puffer)."""
import json, struct, sys, pathlib, ctypes
ROOT = pathlib.Path(__file__).resolve().parents[2]
V2 = ROOT / 'v2'
sys.path.insert(0, str(ROOT / 'uni' / 'bindings' / 'python'))
sys.path.insert(0, str(V2)); sys.path.insert(0, str(ROOT / 'solo'))
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE, UC_PROT_ALL
from unicorn import m68k_const as mk
import common as C

BASE = C.BASE
STOCK = (ROOT / 'out' / 'section_3_MAIN_OS.bin').read_bytes()
LATCH = json.load(open(ROOT / 'elektron-model-tweaks/tweaks/model-cycles_OS1.13/01-latching-mute.json'))
V1_ORDER = ['62-mute-solo', '63-live-mute', '64-hold-mute-v3', '65-delay-notes', '66-chorus', '67-phaser', '68-digi-delay',
            '69-razer', '70-mod-delays', '71-strum', '72-load-meter', '73-groove']
V2_IDS = ['core', 'mute-solo', 'live-mute', 'hold-mute', 'delay-notes', 'reverb-fx', 'delay-fx', 'strum', 'load-meter', 'groove',
          'control-mode', 'trig-select', 'fill2', 'track-filter', 'lfo-amount', 'direct-jump']
V1SYM = {n: json.load(open(ROOT / 'solo' / f'{n}.json')).get('symbols', {}) for n in V1_ORDER}
V2P = {}
for f in sorted((V2 / 'out').glob('[0-9][0-9]-*.json')):
    t = json.load(open(f)); V2P[t['id']] = t
V2SYM = {k: {s: int(v, 16) for s, v in t.get('symbols', {}).items() if isinstance(v, str) and v.startswith('0x')} for k, t in V2P.items()}

RET, STACK = 0x4E000000, 0x4F000000            # Ruecksprung-Stopp ; Stack (0x4F000000 +- 64 K)
PATB = 0x4F100000                              # Pattern B im Emulator (Kopf bei PATB + HDR)
EVT = 0x4F0F0000                               # Encoder-Ereignis
HEAP0 = 0x4F030000
KEEP = [mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6, mk.UC_M68K_REG_D7,
        mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6]


def apply(img, t):
    b = bytearray(img)
    for w in t['writes']:
        n = bytes.fromhex(w['new'])
        if 'old' in w:
            o = bytes.fromhex(w['old']); assert b[w['off']:w['off'] + len(o)] == o, (t['id'], hex(w['off'] + BASE))
        b[w['off']:w['off'] + len(n)] = n
    return bytes(b)


def v1_image():
    img = apply(STOCK, LATCH)
    for n in V1_ORDER:
        img = apply(img, json.load(open(ROOT / 'solo' / f'{n}.json')))
    return img


def v2_image(ids=None, latch=True):
    ids = V2_IDS if ids is None else ids
    img = apply(STOCK, LATCH) if latch else STOCK
    for pid in sorted(ids, key=lambda i: V2P[i]['order']):
        img = apply(img, V2P[pid])
    return img


_keep = []
class Emu:
    """Unicorn mit allen Bereichen. stubs: HELD (gehaltene Tasten aus self.held), CONSUME (mitschreiben), COPY (ausfuehren),
    new/delete (Heap). Timer 0xfc07000c beschreibbar."""
    def __init__(s, img, stubs=True):
        u = s.u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); u.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
        u.reg_write(mk.UC_M68K_REG_SR, 0x2700)
        u.mem_map(0x40000000, 0x2000000); u.mem_write(BASE, img)
        buf = ctypes.create_string_buffer(0x10000); _keep.append(buf)
        u.mem_map_ptr(0x4A330000, 0x10000, UC_PROT_ALL, ctypes.addressof(buf))
        u.mem_map_ptr(0x42330000, 0x10000, UC_PROT_ALL, ctypes.addressof(buf))
        for a, n in ((0x4A400000, 0x400000), (0x80000000, 0x10000), (RET, 0x1000), (STACK - 0x10000, 0x20000),
                     (0x4F020000, 0x30000), (EVT, 0x1000), (PATB, 0x10000), (0xFC070000, 0x1000), (0xFC040000, 0x10000)):
            u.mem_map(a, n)
        s.held, s.consumed, s.copies, s.heap = set(), [], [], [HEAP0]
        s.w32(C.CUR_PAT, PATB)
        if stubs:
            for t in (C.HELD, C.CONSUME, C.COPY, 0x400802E0, 0x400802EC):
                u.hook_add(UC_HOOK_CODE, s._stub, begin=t, end=t)
    def w32(s, a, v): s.u.mem_write(a, struct.pack('>I', v & 0xffffffff))
    def r32(s, a): return struct.unpack('>I', bytes(s.u.mem_read(a, 4)))[0]
    def r8(s, a): return s.u.mem_read(a, 1)[0]
    def w8(s, a, v): s.u.mem_write(a, bytes([v & 0xff]))
    def cstr(s, a): return bytes(s.u.mem_read(a, 24)).split(b'\0')[0].decode('latin-1')
    def hdr(s, off): return PATB + C.HDR + off
    def _stub(s, u, addr, size, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); ret = s.r32(sp)
        if addr == C.HELD:
            u.reg_write(mk.UC_M68K_REG_D0, 1 if s.r32(sp + 4) in s.held else 0)
        elif addr == C.CONSUME:
            s.consumed.append(s.r32(sp + 4))
            for r in (mk.UC_M68K_REG_D0, mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): u.reg_write(r, 0xBADBAD00)
        elif addr == C.COPY:
            dst, src, n = s.r32(sp + 4), s.r32(sp + 8), s.r32(sp + 12)
            u.mem_write(dst, bytes(u.mem_read(src, n))); s.copies.append((dst, n))
        elif addr == 0x400802E0:
            n = s.r32(sp + 4); u.reg_write(mk.UC_M68K_REG_D0, s.heap[0]); s.heap[0] += (n + 15) & ~15
            if s.heap[0] > 0x4F03F000: s.heap[0] = HEAP0
        u.reg_write(mk.UC_M68K_REG_PC, ret); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    def call(s, entry, *args, count=2000000, regs=None, stop=None):
        """C-Aufruf entry(args); Rueckgabe (d0, Register+Stack ok)."""
        sp = STACK - 0x100
        s.u.mem_write(sp, struct.pack('>I', RET) + b''.join(struct.pack('>I', a & 0xffffffff) for a in args))
        s.u.reg_write(mk.UC_M68K_REG_A7, sp)
        for i, r in enumerate(KEEP): s.u.reg_write(r, 0xC0DE0000 + i)
        for r, v in (regs or {}).items(): s.u.reg_write(r, v)
        s.u.emu_start(entry, stop or RET, count=count)
        good = s.u.reg_read(mk.UC_M68K_REG_A7) == sp + 4 and all(
            s.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP) if r not in (regs or {}))
        return s.u.reg_read(mk.UC_M68K_REG_D0), good
    def enc(s, enc, delta, held=()):
        """Wie der Firmware-Code bei 0x400081b8: jsr <Haken> mit a2 = Ereignis, darunter d5 und d0 auf dem Stack.
        Ergebnis: dict(skipped, passed (Drehung, die weitergeht) oder None, regs ok, sp ok, consumed)."""
        s.held = set(held); s.consumed = []
        s.u.mem_write(EVT, struct.pack('>IIiI', 0, enc, 0, 0)); s.u.mem_write(EVT + 8, bytes([delta & 0xff]))
        sp0 = STACK - 0x200
        s.u.mem_write(sp0, struct.pack('>III', RET, 0xD5D5D5D5, 0xD0D0D0D0)); s.u.reg_write(mk.UC_M68K_REG_A7, sp0)
        s.u.reg_write(mk.UC_M68K_REG_A2, EVT)
        regs = [r for r in KEEP if r != mk.UC_M68K_REG_A2]
        for i, r in enumerate(regs): s.u.reg_write(r, 0xC0DE0000 + i)
        hit = []
        h = s.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (hit.append(1), u.emu_stop()), begin=C.ENC_SKIP, end=C.ENC_SKIP)
        hook = s.u.mem_read(C.H_HOOK, 6)
        assert bytes(hook[:2]) == b'\x4e\xb9', 'Encoder-Haken fehlt'
        s.u.emu_start(struct.unpack('>I', bytes(hook[2:6]))[0], RET, count=200000)
        s.u.hook_del(h)
        sp = s.u.reg_read(mk.UC_M68K_REG_A7)
        res = dict(skipped=bool(hit), consumed=list(s.consumed),
                   regs=all(s.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(regs)) and s.u.reg_read(mk.UC_M68K_REG_A2) == EVT)
        if hit:
            res.update(passed=None, sp=sp == sp0 + 12)
        else:
            v = s.r32(sp); res.update(passed=struct.unpack('>i', struct.pack('>I', v))[0], sp=sp == sp0)
        return res


ok = True
def chk(name, cond):
    global ok
    ok &= bool(cond); print('ok  ' if cond else 'FAIL', name); return cond


def done():
    print('GESAMT', 'ok' if ok else 'FEHLER'); sys.exit(0 if ok else 1)
