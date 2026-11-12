# pad-mode (v2, Patch 21, smp27): PAD-Spuren. Eigener Code im Emulator, Firmware-Funktionen gestubbt (Aufrufe mitgeschrieben):
# Sequencer-Sperre SQS, Abspielen PLAY, TRACK + FUNC + Trig (PTSK ueber Core TSVK, smp28), Trig gedrueckt (PPR), FUNC + Trig (PFN),
# LED-Filter (PLSF), LED-Filter-Kette des Cores (LEDF).
import struct
from rig import *
import g2_pad as G

IMG = v2_image()
S, CS = V2SYM['pad-mode'], V2SYM['core']
hp = PATB + C.HDR + C.P_PAD
TKS = C.PIMG(C.TKSLOTS) - BASE
chk('Haken: Grid 0x40022c22 / 0x40022cda, Ereignisbau 0x400548ce, LED_SET 0x40005f86 (Core); Grid-Trig 0x400223fa wieder Stock;'
    ' TRACK-Tasten: Core TSVK, Slot 0 = PTSK, Slot 1 = TSK2 (control-mode)',
    IMG[0x400223FA - BASE:][:6] == STOCK[0x400223FA - BASE:][:6] and IMG[G.PPR_HOOK - BASE:][:6] == C.jmp(S['PPR'])
    and struct.unpack('>II', IMG[TKS:TKS + 8]) == (S['PTSK'], V2SYM['control-mode']['TSK2'])
    and struct.unpack('>I', IMG[C.TSV_KEY_SLOT - BASE:][:4])[0] == CS['TSVK']
    and IMG[G.PFN_HOOK - BASE:][:6] == C.jmp(S['PFN']) and IMG[G.SQS_HOOK - BASE:][:6] == C.jmp(S['SQS'])
    and IMG[0x40005F86 - BASE:][:6] == C.jmp(CS['LEDF']))

e = Emu(IMG)
log = []
UI, KIT, TOBJ, VIEW, EVT_OBJ = 0x4F041000, 0x4F042000, 0x4F043000, 0x4F044000, 0x4F045000
st = dict(active=2, muted=set(), note=set(), ev=EVT_OBJ)
def stub(addr, name, ret):
    def f(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); args = tuple(e.r32(sp + 4 + 4 * i) for i in range(6))
        sr = u.reg_read(mk.UC_M68K_REG_SR)
        log.append((name, args, sr, e.r8(S['MANUAL'])))
        r = ret(args) if callable(ret) else ret
        for x in (mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): u.reg_write(x, 0xBAD)
        u.reg_write(mk.UC_M68K_REG_D0, r & 0xffffffff); u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, f, begin=addr, end=addr)
for addr, name, ret in ((C.SEL_A, 'A', 0x4F04F000), (C.SEL_B, 'B', 0x4F04F100), (C.SEL_C, 'C', lambda a: st['active']),
                        (G.KIT_OF, 'kit', KIT), (G.MUTED, 'muted', lambda a: 1 if a[1] in st['muted'] else 0),
                        (G.EVQ, 'evq', 0), (G.UIS, 'ui', UI), (G.U_SET, 'uset', 0),
                        (G.U_ACT, 'uact', 0), (G.REDRAW, 'redraw', 0), (G.HAS_NOTE, 'has', lambda a: 1 if a[1] in st['note'] else 0),
                        (G.TRIG_ON, 'on', 0), (G.TRIG_DEL, 'del', 0), (G.LED_OF, 'ledof', lambda a: 0x20 + 2 * a[0])):
    stub(addr, name, ret)
# Pattern / Kit fuer PLAY: Spur n bei PATB + 0x2d2 n
PATR = PATB                                       # PATP == CUR_PAT (0x40a7887c): Pattern = Puffer B des Pruefstands
e.u.mem_map(0x4F070000, 0x1000)
e.w32(G.KITP, 0x4F070000)
def trk(t): return PATR + G.TSTRIDE * t

# ---------------- SQS
def sqs(track, manual):
    e.w8(S['MANUAL'], manual); sp = STACK - 0x300
    e.u.mem_write(sp, struct.pack('>7I', RET, track, PATB, 0x4F070000, 5, 0, 0)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    hit = []
    h = e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (hit.append(a), u.emu_stop()), begin=G.SQS_BACK, end=G.SQS_BACK)
    e.u.emu_start(S['SQS'], RET, count=2000); e.u.hook_del(h)
    nsp = e.u.reg_read(mk.UC_M68K_REG_A7)
    if hit: return 'firmware', nsp == sp - 60 and e.u.reg_read(mk.UC_M68K_REG_D1) == 1
    return 'skip', e.u.reg_read(mk.UC_M68K_REG_D0) == 0 and nsp == sp + 4
e.w8(hp, 0b000101)
r = [sqs(t, 0) for t in range(6)] + [sqs(0, 1)]
chk('SQS: PAD-Spuren 1 / 3 ohne Ereignis, andere Spuren und MANUAL -> Ereignisbau der Firmware (Prolog) %s' % [x[0] for x in r],
    [x[0] for x in r] == ['skip', 'firmware', 'skip', 'firmware', 'firmware', 'firmware', 'firmware'] and all(x[1] for x in r))
e.w32(C.CUR_PAT, 0); r = sqs(0, 0); e.w32(C.CUR_PAT, PATB)
chk('SQS: Pattern-Zeiger des Aufrufs gilt (Kopf am uebergebenen Pattern)', r[0] == 'skip')

# ---------------- PLAY
def play(t, step):
    log.clear(); e.u.mem_write(trk(t) + G.T_PROB, bytes([37])); e.u.mem_write(trk(t) + G.T_COND + step, bytes([9]))
    e.u.reg_write(mk.UC_M68K_REG_SR, 0x2000)
    _, good = e.call(S['PLAY'], t, step, count=20000)
    return good, list(log), e.r8(trk(t) + G.T_PROB), e.r8(trk(t) + G.T_COND + step), e.u.reg_read(mk.UC_M68K_REG_SR) & 0x700, e.r8(S['MANUAL'])
seen = {}
def evb_probe(a):
    seen['prob'] = e.r8(trk(a[0]) + G.T_PROB); seen['cond'] = e.r8(trk(a[0]) + G.T_COND + a[3]); return st['ev']
stub(G.EVB, 'evb', evb_probe)
st['sends'] = 0
for addr, name, ret in ((G.M_PROJ, 'proj', 0x4F0F0000), (G.M_TRKO, 'trko', lambda a: 0x4F0F1000 + a[1]),
                        (G.M_SENDS, 'sends', lambda a: st['sends']), (G.M_CHAN, 'chan', lambda a: 3 + a[1]),
                        (G.M_NON, 'non', 1), (G.M_NOFF, 'noff', 0)):
    stub(addr, name, ret)
MIDI_STUBS = ('proj', 'trko', 'sends', 'chan', 'non', 'noff')
e.u.mem_write(EVT_OBJ + G.EV_VEL, bytes([77, 0]))
r = play(3, 7)
ev = [x for x in r[1] if x[0] == 'evb']
q = [x for x in r[1] if x[0] == 'evq']
chk('PLAY(Spur 4, Step 8): Ereignisbau (Spur, Pattern, Kit, Step, 0, 0) mit Interrupts aus, MANUAL, Wahrscheinlichkeit 100 und '
    'Bedingung 0xff waehrend des Baus; Ereignis +0xc = 2 in die Warteschlange; danach alles zurueck (%d / %d), SR wieder offen'
    % (r[2], r[3]), r[0] and ev and ev[0][1] == (3, PATR, 0x4F070000, 7, 0, 0) and (ev[0][2] & 0x700) == 0x700 and ev[0][3] == 1
    and seen == {'prob': 100, 'cond': 0xFF} and q and q[0][1][0] == EVT_OBJ and e.r32(EVT_OBJ + 12) == 2 and (q[0][2] & 0x700) == 0x700
    and r[2] == 37 and r[3] == 9 and r[4] == 0 and r[5] == 0)
st['muted'] = {3}; r = play(3, 7); st['muted'] = set()
chk('PLAY: gemutete Spur spielt nicht', r[0] and not [x for x in r[1] if x[0] in ('evb', 'evq')] and r[2] == 37)
st['ev'] = 0; r = play(1, 0); st['ev'] = EVT_OBJ
chk('PLAY: kein Ereignis (Step leer) -> nichts in die Warteschlange, alles zurueck', r[0] and not [x for x in r[1] if x[0] == 'evq'] and r[2] == 37 and r[3] == 9)
r1, r2 = play(6, 0), play(0, 64)
chk('PLAY: Spur > 5 / Step > 63 -> nichts', r1[0] and r2[0] and not [x for x in r1[1] + r2[1] if x[0] == 'evb'])

# ---------------- PTSK (TRACK + RETRIG + Trig 1..6, smp42) ueber den Core (TSVK), control-mode dahinter, Firmware zuletzt
EVK, TV = 0x4F04E200, 0x4F04E300
fw = []
def fw_key(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); fw.append((e.r32(sp + 4), e.r32(sp + 8)))
    u.reg_write(mk.UC_M68K_REG_D0, 7); u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
e.u.hook_add(UC_HOOK_CODE, fw_key, begin=C.TSV_KEY, end=C.TSV_KEY)
import g2_control as GC
stub(GC.LED_CTX, 'ledctx', 0x4F0AA000); stub(GC.LED_SET, 'ledset', 0)          # LEDs von control-mode (CALEDS)
def tsv(code, flags, held):
    log.clear(); fw.clear(); e.held = set(held); e.w32(EVK + 0x0C, code); e.w32(EVK + 0x10, flags); e.w32(C.VARS + C.V_VAL, 0)
    d0, good = e.call(CS['TSVK'], TV, EVK, count=50000)
    return d0, good, e.r8(hp), e.r8(C.CA_SEL), list(fw)
e.w8(hp, 0); e.w8(C.CA_SEL, 0x80)
r = tsv(17, 1, (2, 4))
chk('TRACK + RETRIG + Trig 2: Spur 2 PAD (Byte 57 = 2), Popup %s / %s / %s, behandelt, Control-All unberuehrt, Register ok'
    % (e.cstr(e.r32(C.VARS + C.V_L1)), e.cstr(e.r32(C.VARS + C.V_L2)), e.cstr(e.r32(C.VARS + C.V_VAL))),
    r[0] == 1 and r[1] and r[2] == 2 and r[3] == 0x80 and r[4] == [] and e.cstr(e.r32(C.VARS + C.V_L1)) == 'Pad Mode'
    and e.cstr(e.r32(C.VARS + C.V_L2)) == 'Track 2' and e.cstr(e.r32(C.VARS + C.V_VAL)) == 'On')
r = tsv(17, 0, (2, 4)); r2 = tsv(17, 1, (2, 4)); v2 = e.cstr(e.r32(C.VARS + C.V_VAL))
r3 = tsv(17, 1, (2,)); e.w8(C.CA_SEL, 0x80); r6 = tsv(17, 1, (2, 1)); r4 = tsv(22, 1, (2, 4)); r5 = tsv(1, 1, (2, 4))
r7 = [tsv(4, f, (2,)) for f in (1, 0, 16)]
chk('Loslassen verbraucht; nochmal -> aus (Off); ohne RETRIG: control-mode (Control All Spur 2); TRACK + FUNC + Trig: nicht mehr PAD '
    '(smp42, FUNC = latching-mute); Trig 7 / FUNC: Firmware; RETRIG selbst mit TRACK: verbraucht %s'
    % [hex(r3[3]), r4[4], r5[4], [x[0] for x in r7]],
    r[0] == 1 and r[2] == 2 and r2[2] == 0 and v2 == 'Off' and r3[0] == 1 and r3[2] == 0 and r3[3] == 0x82 and r3[4] == []
    and r6[2] == 0 and r4[0] == r5[0] == 7 and r4[4] == r5[4] == [(TV, EVK)] and r4[2] == r5[2] == 0
    and all(x[0] == 1 and x[4] == [] and x[2] == 0 for x in r7))
e.w8(C.CA_SEL, 0)

# ---------------- PKB (smp29): KeyboardView (Trigs ohne REC) -> PAD-Spur spielt Steps statt chromatisch
chk('Vtable der KeyboardView 0x400ff9cc = PKB (Firmware 0x4001a0d2)', struct.unpack('>I', IMG[G.KB_SLOT - BASE:][:4])[0] == S['PKB']
    and struct.unpack('>I', STOCK[G.KB_SLOT - BASE:][:4])[0] == G.KB_KEY)
kst = dict(rec=0, alt=0, page=1)
stub(G.UI_REC, 'rec', lambda a: kst['rec']); stub(G.UI_ALT, 'alt', lambda a: kst['alt']); stub(G.PAGE_OF, 'page', lambda a: kst['page'])
kfw = []
def kb_fw(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); kfw.append((e.r32(sp + 4), e.r32(sp + 8)))
    u.reg_write(mk.UC_M68K_REG_D0, 5); u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
e.u.hook_add(UC_HOOK_CODE, kb_fw, begin=G.KB_KEY, end=G.KB_KEY)
def pkb(code, flags, held=(), pad=True, **k):
    kst.update(dict(rec=0, alt=0, page=1)); kst.update(k); log.clear(); kfw.clear(); e.held = set(held)
    e.w8(hp, 0b000100 if pad else 0); st['active'] = 2
    e.w32(EVK + 0x0C, code); e.w32(EVK + 0x10, flags)
    d0, good = e.call(S['PKB'], TV, EVK, count=50000)
    return d0, good, [x[1][:4] for x in log if x[0] == 'evb'], list(kfw)
r = [pkb(18, 1), pkb(18, 1, page=0), pkb(31, 1, page=3), pkb(18, 0)]
chk('Ohne REC, PAD-Spur 3: Trig 3 spielt Step 19 (Seite 2) / Step 3 (Seite 1), Trig 16 Seite 4 = Step 64; Loslassen verbraucht ohne'
    ' Spielen; Register ok %s' % [x[2] for x in r],
    all(x[0] == 1 and x[1] and x[3] == [] for x in r) and r[0][2] == [(2, PATR, 0x4F070000, 18)] and r[1][2] == [(2, PATR, 0x4F070000, 2)]
    and r[2][2] == [(2, PATR, 0x4F070000, 63)] and r[3][2] == [])
r = [pkb(18, 1, rec=1), pkb(18, 1, alt=1), pkb(18, 1, held=(1,), pad=False), pkb(18, 1, pad=False), pkb(7, 1), pkb(32, 1)]
chk('REC / anderer UI-Modus / keine PAD-Spur (auch mit FUNC) / GATE / Taste 32: Konsument der Firmware (chromatisch), nichts gespielt',
    all(x[0] == 5 and x[1] and x[2] == [] and x[3] == [(TV, EVK)] for x in r))
r = [pkb(18, 1, held=(1,)), pkb(18, 0, held=(1,))]
chk('smp30: FUNC + Trig auf der PAD-Spur ohne REC: verbraucht, nichts gespielt, nicht chromatisch',
    all(x[0] == 1 and x[1] and x[2] == [] and x[3] == [] for x in r))
# GLR (smp30): REC-Pruefung der Grid-LEDs
chk('Haken 0x40021e28 = jsr GLR + 3 nop', IMG[G.GLR_HOOK - BASE:][:12] == C.jsr(S['GLR']) + bytes.fromhex('4e71') * 3)
def glr(rec, pad):
    kst['rec'] = rec; e.w8(hp, 0b000100 if pad else 0); st['active'] = 2
    sp = STACK - 0x300; e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    for r_, v in ((mk.UC_M68K_REG_D2, 0xD2), (mk.UC_M68K_REG_D3, 0xD3), (mk.UC_M68K_REG_D5, 0xD5), (mk.UC_M68K_REG_D7, 0xD7),
                  (mk.UC_M68K_REG_A2, 0xA2), (mk.UC_M68K_REG_A3, 0xA3), (mk.UC_M68K_REG_A5, 0x4006B978)):
        e.u.reg_write(r_, v)
    e.u.emu_start(G.GLR_HOOK, G.GLR_HOOK + 12, count=5000)
    good = e.u.reg_read(mk.UC_M68K_REG_A7) == sp and all(e.u.reg_read(r_) == v for r_, v in ((mk.UC_M68K_REG_D2, 0xD2),
            (mk.UC_M68K_REG_D3, 0xD3), (mk.UC_M68K_REG_D5, 0xD5), (mk.UC_M68K_REG_D7, 0xD7), (mk.UC_M68K_REG_A2, 0xA2),
            (mk.UC_M68K_REG_A3, 0xA3), (mk.UC_M68K_REG_A5, 0x4006B978)))
    return e.u.reg_read(mk.UC_M68K_REG_D0) & 0xff, good
r = [glr(1, False), glr(0, False), glr(0, True), glr(1, True)]
chk('Grid-LEDs: Steps zeigen mit REC oder aktiver PAD-Spur, sonst wie Stock (Wiedergabe-Licht) %s; Register / Stapel ok' % [x[0] for x in r],
    [bool(x[0]) for x in r] == [True, False, True, True] and all(x[1] for x in r))

# ---------------- smp34: Velocity (PLAYV), MIDI-Ausgang der Trig-Tasten (PLAY -> MOUT), MIDI-Eingang (PADM)
def playv(t, step, vel):
    log.clear(); e.u.mem_write(EVT_OBJ + G.EV_VEL, bytes([77, 0]))
    d0, good = e.call(S['PLAYV'], t, step, vel & 0xffffffff, count=20000)
    return d0, good, e.r8(EVT_OBJ + G.EV_VEL), e.r8(EVT_OBJ + G.EV_VEL + 1), [x[0] for x in log if x[0] in ('evb', 'evq')]
r = [playv(2, 5, v) for v in (90, 1, 127, -1, 0, 128, 200)]
st['muted'] = {2}; rm = playv(2, 5, 90); st['muted'] = set()
chk('PLAYV: Velocity 1..127 ersetzt die des Steps (Ereignis +0x16, vor der Warteschlange), -1 / 0 / >127 lassen sie; d0 = gespielte '
    'Velocity, gemutet 0 %s' % [(x[0], x[2]) for x in r],
    [(x[0], x[2]) for x in r] == [(90, 90), (1, 1), (127, 127), (77, 77), (77, 77), (77, 77), (77, 77)] and all(x[1] and x[4] == ['evb', 'evq'] for x in r)
    and all(x[3] == 0 for x in r[:3]) and rm[0] == 0 and rm[4] == [])
def playk(t, step, sends):
    log.clear(); st['sends'] = sends; e.u.mem_write(EVT_OBJ + G.EV_VEL, bytes([77, 0]))
    _, good = e.call(S['PLAY'], t, step, count=40000)
    return good, [(x[0], x[1][:3]) for x in log if x[0] in MIDI_STUBS + ('evb',)]
r1, r0 = playk(3, 18, 1), playk(3, 18, 0)
chk('Trig-Taste (PLAY): Step 19 (Seite 2, Trig 3) -> Note-On / Note-Off 38 mit der Velocity des Steps auf dem Kanal der Spur '
    '(0x40012e82); sendet die Spur kein MIDI (0x40016e90 = 0): nichts %s' % r1[1],
    r1[0] and r0[0] and [(x[0], x[1][:2]) for x in r1[1] if x[0] in ('non', 'noff', 'chan')] == [('chan', (0x4F04F100, 3)), ('non', (6, 38)), ('noff', (6, 38))]
    and [x[1][2] for x in r1[1] if x[0] == 'non'] == [77]
    and [x[1][0] for x in r1[1] if x[0] == 'sends'] == [0x4F0F1003] and [x[1][:2] for x in r1[1] if x[0] == 'trko'] == [(0x4F0F0000, 3)] and not [x for x in r0[1] if x[0] in ('non', 'noff')])
chk('Haken 0x400819fc (Note-On-Verteiler) = jsr PADM + nop', IMG[G.MIDI_HOOK - BASE:][:8] == C.jsr(S['PADM']) + bytes.fromhex('4e71'))
def padm(mask, note, vel, pads, page=1):
    log.clear(); kst['page'] = page; e.w8(hp, pads); e.u.mem_write(EVT_OBJ + G.EV_VEL, bytes([77, 0]))
    sp = STACK - 0x300; e.u.mem_write(sp, bytes(0x28) + struct.pack('>IIII', 9, note, vel, 0))   # Rahmen des Verteilers: +0x28 Kanal, +0x2c Note, +0x30 Velocity
    e.u.reg_write(mk.UC_M68K_REG_A7, sp); e.u.reg_write(mk.UC_M68K_REG_D3, 0xABCD0000 | mask)
    for r_, v in ((mk.UC_M68K_REG_D2, 0xD2), (mk.UC_M68K_REG_D4, 0xD4), (mk.UC_M68K_REG_D6, 0xD6), (mk.UC_M68K_REG_D7, 0xD7),
                  (mk.UC_M68K_REG_D5, 0x55), (mk.UC_M68K_REG_A4, 0xA4), (mk.UC_M68K_REG_A3, 0xA3)):
        e.u.reg_write(r_, v)
    e.u.emu_start(G.MIDI_HOOK, G.MIDI_HOOK + 8, count=50000)
    rg = [e.u.reg_read(x) for x in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D6, mk.UC_M68K_REG_D7, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A3)]
    ok_ = e.u.reg_read(mk.UC_M68K_REG_A7) == sp and rg == [0xD2, 0xD4, 0xD6, 0xD7, 0xA4, 0xA3] and e.u.reg_read(mk.UC_M68K_REG_D5) == 0 \
        and e.u.reg_read(mk.UC_M68K_REG_A2) == G.MIDI_LIVE
    return e.u.reg_read(mk.UC_M68K_REG_D3), ok_, [(x[1][0], x[1][3]) for x in log if x[0] == 'evb'], e.r8(EVT_OBJ + G.EV_VEL), \
        [x[0] for x in log if x[0] in ('non', 'noff')]
r = [padm(0b000110, 38, 100, 0b000100), padm(0b000110, 51, 64, 0b000110, page=3), padm(0b000100, 60, 100, 0b000100),
     padm(0b000101, 35, 100, 0b000100), padm(0b000011, 40, 100, 0)]
chk('PADM: Note 38 auf Kanal von Spur 2 (PAD) + 3: Spur 3 spielt Step 19 (Seite 2) mit Velocity 100, Spur 2 bleibt fuer die Firmware;'
    ' Note 51 Seite 4 -> Step 64 auf beiden PAD-Spuren; Note 60 / 35 auf PAD: nichts (nie chromatisch); keine PAD-Spur: unveraendert;'
    ' Register / Stapel / d5 = 0 / a2 = 0x4008171e; kein MIDI-Echo %s' % [(hex(x[0]), x[2]) for x in r],
    [x[0] for x in r] == [0b000010, 0, 0, 0b000001, 0b000011] and all(x[1] and x[4] == [] for x in r)
    and r[0][2] == [(2, 18)] and r[0][3] == 100 and r[1][2] == [(1, 63), (2, 63)] and r[1][3] == 64 and r[2][2] == [] and r[3][2] == []
    and r[4][2] == [])

# ---------------- PPR / PFN (aktive Spur 3)
def grid(entry, regs, stops):
    sp = STACK - 0x300; e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    for r_, v in regs.items(): e.u.reg_write(r_, v)
    hit = []
    hs = [e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (hit.append(a), u.emu_stop()), begin=x, end=x) for x in stops]
    e.u.emu_start(entry, 0, count=50000)
    for h in hs: e.u.hook_del(h)
    return (hit[0] if hit else None), e.u.reg_read(mk.UC_M68K_REG_A7) - sp
st['active'] = 2
def ppr(pad):
    log.clear(); e.w8(hp, 0b000100 if pad else 0)
    e.u.mem_write(trk(2) + G.T_PROB, bytes([50]))
    pc, dsp = grid(S['PPR'], {mk.UC_M68K_REG_A3: 5, mk.UC_M68K_REG_D4: TOBJ, mk.UC_M68K_REG_A2: VIEW, mk.UC_M68K_REG_A5: G.UIS},
                   (G.GRID_DONE, G.PPR_BACK))
    return pc, dsp, e.u.reg_read(mk.UC_M68K_REG_D2), [(x[0], x[1][:3]) for x in log if x[0] not in ('A', 'B', 'C', 'kit', 'muted') + MIDI_STUBS]
r = ppr(True)
names = [x for x in r[3] if x[0] != 'ui']
chk('PAD-Spur, Trig 6 gedrueckt: halten (UI, 5, 1), keine Loslass-Aktion (UI, 5, 0), Step 6 spielen, neu zeichnen, behandelt %s' % names,
    r[0] == G.GRID_DONE and r[1] == 0 and r[2] == 1 and [x[0] for x in names] == ['uset', 'uact', 'evb', 'evq', 'redraw']
    and names[0][1] == (UI, 5, 1) and names[1][1] == (UI, 5, 0) and names[2][1] == (2, PATR, 0x4F070000) and names[4][1][0] == VIEW)
r = ppr(False)
chk('Normale Spur: Firmware (jsr (a5), pea 1, weiter bei 0x40022c28)', r[0] == G.PPR_BACK and r[1] == -4 and e.r32(e.u.reg_read(mk.UC_M68K_REG_A7)) == 1
    and r[3] == [('ui', (0, 0, 0))][:0] + [x for x in r[3] if x[0] == 'ui'])
def pfn(pad, note):
    log.clear(); e.w8(hp, 0b000100 if pad else 0); st['note'] = {5} if note else set()
    pc, dsp = grid(S['PFN'], {mk.UC_M68K_REG_A3: 5, mk.UC_M68K_REG_D4: TOBJ, mk.UC_M68K_REG_A2: VIEW, mk.UC_M68K_REG_A4: G.UIS},
                   (G.GRID_DONE, G.PFN_BACK))
    return pc, dsp, [(x[0], x[1][:3]) for x in log if x[0] in ('on', 'del', 'uact')]
r1, r2, r3 = pfn(True, False), pfn(True, True), pfn(False, False)
chk('FUNC + Trig auf PAD-Spur: leer -> anlegen (Spur, 5, 1), Trig da -> loeschen (Spur, 5, 0), Aktion 0; normale Spur: Firmware',
    r1[0] == r2[0] == G.GRID_DONE and r1[2] == [('on', (TOBJ, 5, 1)), ('uact', (UI, 5, 0))] and r2[2] == [('del', (TOBJ, 5, 0)), ('uact', (UI, 5, 0))]
    and r3[0] == G.PFN_BACK and r3[1] == -4)

# ---------------- LED: PLSF und die Kette des Cores
def plsf(led, state, held):
    e.held = set(held); e.u.reg_write(mk.UC_M68K_REG_D0, led); e.u.reg_write(mk.UC_M68K_REG_D1, state)
    _, good = e.call(S['PLSF'], regs={mk.UC_M68K_REG_D0: led, mk.UC_M68K_REG_D1: state}, count=20000)
    return e.u.reg_read(mk.UC_M68K_REG_D1), good
e.w8(hp, 0b010001); e.w32(C.TIMER, 1 << C.SEL_BLINK_BIT)
r = [plsf(0x20 + 2 * t, 3, (2, 4)) for t in range(7)] + [plsf(0x20, 3, ()), plsf(0x20, 3, (2,)), plsf(0x20, 3, (4,)), plsf(0x20, 3, (2, 1))]
e.w32(C.TIMER, 0); r2 = plsf(0x20, 3, (2, 4)); e.w32(C.TIMER, 1 << C.SEL_BLINK_BIT)
chk('PLSF: TRACK + RETRIG gehalten -> Trig 1..6 = PAD schnell blinkend (an 2 / aus 1) / nicht (1) %s; Trig 7 / ohne / nur TRACK / '
    'nur RETRIG / TRACK + FUNC unveraendert' % [x[0] for x in r + [r2]],
    [x[0] for x in r] == [2, 1, 1, 1, 2, 1, 3, 3, 3, 3, 3] and r2[0] == 1 and all(x[1] for x in r))
def ledf(led, state, held):
    e.held = set(held); sp = STACK - 0x300
    e.u.mem_write(sp, struct.pack('>5I', 0x4E000F00, 0x4F0AA000, led, state, 0x404A8CB8)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e.u.reg_write(mk.UC_M68K_REG_D2, 0xD2D2); e.u.reg_write(mk.UC_M68K_REG_D3, 0xD3D3); e.u.reg_write(mk.UC_M68K_REG_A2, 0xA2A2)
    hit = []
    h = e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (hit.append(a), u.emu_stop()), begin=0x40005F8E, end=0x40005F8E)
    e.u.emu_start(CS['LEDF'], 0, count=50000); e.u.hook_del(h)
    nsp = e.u.reg_read(mk.UC_M68K_REG_A7)
    ok_ = hit == [0x40005F8E] and nsp == sp - 12 and e.r32(nsp) == 0xD2D2 and e.r32(nsp + 4) == 0xD3D3 and e.r32(nsp + 8) == 0xA2A2
    return ok_, e.r32(sp + 12)
e.w8(C.CA_SEL, 0x80 | 0b000010)
r = [ledf(0x22, 3, ()), ledf(0x22, 3, (2,)), ledf(0x22, 3, (2, 4)), ledf(0x20, 3, (2, 4)), ledf(0x2C, 2, (2, 4))]
chk('LEDF (Core): Filter-Kette control-mode (TRACK) + pad-mode (TRACK + RETRIG, zuletzt), Prolog von LED_SET nachgespielt %s' % [x[1] for x in r],
    all(x[0] for x in r) and [x[1] for x in r] == [3, 1, 1, 2, 2])
done()
