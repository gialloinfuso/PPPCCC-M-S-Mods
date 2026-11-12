# browser-scroll (Teil des Cores, v2.3, eigener Code g2_browserscroll.py): BS im Emulator (Text-Funktion, UI gestubbt),
# Namen verschiedener Laenge ueber viele Takte gegen ein Python-Modell (0.17 s je Zeichen, Pausen am Anfang / Ende,
# passende Namen bleiben stehen, neuer Name = von vorn). Ist drumkillas Tweak vorhanden: zusaetzlich gleiches Ergebnis.
import json, struct
from rig import *
import g2_browserscroll as B

NAME, DRAW = 0x4F040000, []


def emu(img):
    e = Emu(img)
    def stub(u, addr, size, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); ret = e.r32(sp)
        if addr == B.TXT_DRAW:
            DRAW.append(e.r32(sp + 24) - NAME)
        u.reg_write(mk.UC_M68K_REG_D0, 0x4F041000 if addr == B.UIS else 0)
        u.reg_write(mk.UC_M68K_REG_PC, ret); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    for a in (B.TXT_DRAW, B.UIS, B.UI_DIRTY):
        e.u.hook_add(UC_HOOK_CODE, stub, begin=a, end=a)
    return e


def run(e, entry, seq):
    out = []
    for name, width, tick in seq:
        e.u.mem_write(NAME, name.encode() + b'\0'); e.w32(B.TICK, tick); DRAW.clear()
        d0, good = e.call(entry, 1, 2, 3, 4, width, NAME)
        out.append((DRAW[0] if DRAW else None, good))
    return out


def model(seq):
    st = dict(id=None, off=0, t=0, p=0); out = []
    for name, width, tick in seq:
        k = (len(name) << 16) + sum(name.encode())
        if k != st['id']:
            st.update(id=k, off=0, p=0)
        elif (tick - st['t']) >> 8:
            st['t'] = tick; mx = max(len(name) - width, 0)
            if st['off'] < mx and st['off']:
                st['off'] += 1
            else:
                d1 = -1 if st['off'] >= mx else 0
                st['p'] += 1
                if st['p'] >= 3: st['p'] = 0; st['off'] = d1 + 1
        out.append((st['off'], True))
    return out


seq = []
t = 1000
for name, w in (('Kick', 10), ('A very long sample name.wav', 10), ('Exactly10!', 10), ('Snare long name', 8),
                ('A very long sample name.wav', 10)):
    for i in range(60):
        t += 200 if i % 3 else 300; seq.append((name, w, t))
img = v2_image(['core', 'browser-scroll'], latch=False)
e = emu(img)
res = run(e, B.code()[1]['BS'], seq)
chk('Text-Funktion jedes Mal aufgerufen, Register und Stapel', all(r[0] is not None and r[1] for r in res))
chk('Versatz wie das Modell (%d Aufrufe: 5 Namen, Laufschrift, Pausen, passende Namen stehen)' % len(seq), res == model(seq))
chk('langer Name laeuft bis zum Ende (17 Zeichen ueber), kurzer bleibt bei 0',
    max(r[0] for r in res[60:120]) == 17 and all(r[0] == 0 for r in res[:60]))
chk('Haken: 0x400a559e jsr BS', bytes(e.u.mem_read(B.CALL, 6)) == bytes.fromhex('4eb9') + struct.pack('>I', B.code()[1]['BS']))
dk = ROOT / 'elektron-model-tweaks/tweaks/model-cycles_OS1.13/03-browser-scroll.json'
if dk.exists():
    e2 = emu(apply(STOCK, json.load(open(dk))))
    chk('gleiches Ergebnis wie drumkillas browser-scroll', run(e2, 0x40147F22, seq) == res)
else:
    print('(drumkillas Tweak nicht vorhanden: kein Vergleich)')
done()
