# Hold-Mute v3 auf der offiziellen Cycles OS 1.13 (Port aus v21). Gleiche Faelle wie test_holdmute3.py.
import hashlib, json, struct, sys
sys.path.insert(0,'uni/bindings/python')
from unicorn import *
from unicorn import m68k_const as mk
BASE=0x40000400
img=bytearray(open('out/section_3_MAIN_OS.bin','rb').read())
T=json.load(open('solo/64-hold-mute-v3.json'))
for w in T['writes']:
    o=bytes.fromhex(w['old']); assert img[w['off']:w['off']+len(o)]==o; img[w['off']:w['off']+len(o)]=bytes.fromhex(w['new'])
H1,H2,HC=0x4001d05e,0x4001d0fc,0x400081f2
ON_AFTER,OFF_AFTER,TICKNEXT=0x4001d064,0x4001d102,0x40090f48
PLAY=0x4005481a; playing=[1]
GETM,SETM,SING,KITF=0x4001263c,0x4001381c,0x400cf866,0x4000eb90
STACK=0x4f000000; RET=0x4e000000; TMR=0xfc07000c
ST=int(T['symbols']['state'],16); TICK=HC
uc=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN); uc.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
uc.mem_map(0x40000000,0x2000000); uc.mem_write(BASE,bytes(img))
uc.mem_map(STACK-0x10000,0x20000); uc.mem_map(RET,0x1000); uc.mem_map(0xfc070000,0x1000)
log=[]; mute=[0]*6
R=lambda r: uc.reg_read(r)
def rd(a): return struct.unpack('>I',uc.mem_read(a,4))[0]
def ret_to_caller(extra=0,d0=None):
    a7=R(mk.UC_M68K_REG_A7)+extra
    if d0 is not None: uc.reg_write(mk.UC_M68K_REG_D0,d0)
    uc.reg_write(mk.UC_M68K_REG_PC,rd(a7)); uc.reg_write(mk.UC_M68K_REG_A7,a7+4)
def hook(uc,addr,size,_):
    a7=R(mk.UC_M68K_REG_A7)
    if addr==ON_AFTER: log.append(('noteon',rd(a7+24),rd(a7+28),rd(a7+32),rd(a7+36),rd(a7+20))); ret_to_caller(16)
    elif addr==OFF_AFTER: log.append(('noteoff',rd(a7+0x14),rd(a7+0x18))); ret_to_caller(12)
    elif addr==SING: ret_to_caller(d0=0x1111)
    elif addr==KITF: ret_to_caller(d0=0x2222 if rd(a7+4)==0x1111 else 0xBAD)
    elif addr==GETM:
        assert rd(a7+4)==0x2222; ret_to_caller(d0=mute[rd(a7+8)])
    elif addr==SETM:
        assert rd(a7+4)==0x2222 and rd(a7+16)==1, (rd(a7+4),rd(a7+16))
        mute[rd(a7+8)]=rd(a7+12); log.append(('setmute',rd(a7+8),rd(a7+12))); ret_to_caller()
    elif addr==PLAY: ret_to_caller(d0=playing[0])
    elif addr==TICKNEXT: log.append(('tick-orig',rd(a7),rd(a7+4),a7)); uc.emu_stop()
    elif addr==RET: uc.emu_stop()
for f in (ON_AFTER,OFF_AFTER,SING,KITF,GETM,SETM,TICKNEXT,RET,PLAY): uc.hook_add(UC_HOOK_CODE,hook,begin=f,end=f)
def settmr(t): uc.mem_write(TMR,struct.pack('>I',t&0xffffffff))
SAV={mk.UC_M68K_REG_A2:0xCAFE0002,mk.UC_M68K_REG_D2:0xD2D2,mk.UC_M68K_REG_D3:0xD3D3}
def callw(entry,args):
    sp=STACK-4*(len(args)+1); uc.mem_write(sp,struct.pack('>I',RET)+b''.join(struct.pack('>I',x&0xffffffff) for x in args))
    uc.reg_write(mk.UC_M68K_REG_A7,sp)
    for k,v in SAV.items(): uc.reg_write(k,v)
    log.clear(); uc.emu_start(entry,0,count=6000); return sp
def regs_ok(): return all(R(k)==v for k,v in SAV.items())
def chk(n,c): print(('ok  ' if c else 'FAIL'),n)
HOLD=0x01A00000; A2=0x11112222
def tick(t):
    settmr(t); sp=STACK-0x200; uc.mem_write(sp,struct.pack('>I',0xABCD)); uc.reg_write(mk.UC_M68K_REG_A7,sp)
    for k,v in SAV.items(): uc.reg_write(k,v)
    log.clear(); uc.emu_start(TICK,0,count=6000); return sp
# Tippen
settmr(1000); callw(H1,[A2,2,60,100,0xffffffff])
chk('Press verschluckt, Zustand gemerkt',log==[] and rd(ST+32)==1000 and rd(ST+36)==61 and rd(ST+40)==100 and regs_ok())
sp=tick(1000+HOLD-1); chk('Tick vor HOLD: nichts, Original weiter, Stack gleich, Register',log==[('tick-orig',0x400081f8,0xABCD,sp-4)] and regs_ok())
settmr(1000+HOLD-1); callw(H2,[A2,2,60])
chk('Release nach Tippen: noteon nachgeholt + noteoff, kein Mute',log==[('noteon',2,60,100,0xffffffff,A2),('noteoff',2,60)] and mute==[0]*6 and regs_ok())
# Halten
settmr(5000); callw(H1,[A2,4,72,90,5])
tick(5000+HOLD-1); chk('Tick < HOLD: kein Mute',mute==[0]*6)
sp=tick(5000+HOLD); chk('Tick >= HOLD: Track 4 gemutet (setMute(kit,4,1,1)), danach Original',log==[('setmute',4,1),('tick-orig',0x400081f8,0xABCD,sp-4)] and mute[4]==1 and regs_ok())
tick(5000+HOLD+10); chk('weiterer Tick: nicht doppelt',log==[('tick-orig',0x400081f8,0xABCD,STACK-0x200-4)])
settmr(5000+HOLD+777); callw(H2,[A2,4,72])
chk('Release nach Halten: entmutet, nichts gespielt',log==[('setmute',4,0)] and mute==[0]*6 and rd(ST+64+4)==0 and regs_ok())
# bereits gemuteter Track
mute[1]=1; settmr(100); callw(H1,[A2,1,50,80,0xffffffff]); tick(100+HOLD+5)
chk('Track schon gemutet (Latch): wird nicht angefasst',log==[('tick-orig',0x400081f8,0xABCD,STACK-0x200-4)])
settmr(100+HOLD+9); callw(H2,[A2,1,50]); chk('  Release: bleibt gemutet, nichts gespielt',mute[1]==1 and log==[])
mute[1]=0
# Release ohne Press, Track>5
settmr(1); callw(H2,[A2,1,40]); chk('Release ohne Press: Original-noteoff',log==[('noteoff',1,40)])
callw(H1,[A2,7,40,1,0xffffffff]); chk('Press Track>5: Original-noteon',log==[('noteon',7,40,1,0xffffffff,A2)])
# Repress waehrend gemutet
settmr(0); callw(H1,[A2,3,40,1,0xffffffff]); tick(HOLD+1); settmr(HOLD+50); callw(H1,[A2,3,40,1,0xffffffff])
settmr(HOLD+60); callw(H2,[A2,3,40]); chk('Re-Press bei gemutetem Track, dann Release: entmutet',mute[3]==0)
# Ueberlauf
settmr(0xFFFFFF00); callw(H1,[A2,1,50,80,0xffffffff]); settmr(0x100); callw(H2,[A2,1,50])
chk('Timer-Ueberlauf (Tippen)',[l[0] for l in log]==['noteon','noteoff'])
settmr(0xFFFFFF00); callw(H1,[A2,1,50,80,0xffffffff]); tick(0xFFFFFF00+HOLD); chk('Ueberlauf Halten: Mute',mute[1]==1)
settmr(0); callw(H2,[A2,1,50]); chk('  Release: entmutet',mute[1]==0)

# Sequencer gestoppt: Pads spielen sofort normal, kein Mute
playing[0]=0; mute[:]=[0]*6
settmr(90000); callw(H1,[A2,1,50,77,0xffffffff])
chk('gestoppt: Note-On sofort (Original), nichts gemerkt', log==[('noteon',1,50,77,0xffffffff,A2)] and rd(ST+16+4)==0 and regs_ok())
tick(90000+2*HOLD); chk('gestoppt + gehalten: kein Mute', mute==[0]*6)
settmr(90000+3*HOLD); callw(H2,[A2,1,50]); chk('gestoppt: Note-Off normal', log==[('noteoff',1,50)] and mute==[0]*6)
playing[0]=1

# Die echte Sequencer-laeuft-Funktion in 1.13 ist dieselbe wie in OS 2.0 (move.l RUN1,d0 ; or.l RUN2,d0 ; rts)
stock=open('out/section_3_MAIN_OS.bin','rb').read()
chk('1.13: 0x4005481a = Sequencer-laeuft wie in OS 2.0 (SHA-256 der 14 Bytes)', hashlib.sha256(stock[PLAY-BASE:PLAY-BASE+14]).hexdigest()=='b5c0eba75ac51645d3a6c96ea0a9fdea57255595b53c59c9903bc50cf2fe8d7d')
