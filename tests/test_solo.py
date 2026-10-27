import json, struct, sys, itertools
sys.path.insert(0,'uni/bindings/python')
from unicorn import *
from unicorn import m68k_const as mk
BASE=0x40000400
img=bytearray(open('out/section_3_MAIN_OS.bin','rb').read())
for name in ('elektron-model-tweaks/tweaks/model-cycles_OS1.13/01-latching-mute.json','solo/62-mute-solo.json'):
    for w in json.load(open(name))['writes']:
        o=bytes.fromhex(w['old']); assert img[w['off']:w['off']+len(o)]==o; img[w['off']:w['off']+len(o)]=bytes.fromhex(w['new'])
GETM,SETM,KEYH,TOGGLE=0x4001263c,0x4001381c,0x4007faf4,0x40013904
LATCH=0x401487ed; ENTRY=0x40167c50; SOLOF=ENTRY+0x10E; SAVED=ENTRY+0x108
STACK=0x4f000000; RET=0x4e000000
def run(muted, latched, func_held, track, solof=0, saved=None):
    uc=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN); uc.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
    uc.mem_map(0x40000000,0x2000000); uc.mem_write(BASE,bytes(img))
    uc.mem_map(STACK-0x10000,0x20000); uc.mem_map(RET,0x1000); uc.mem_write(RET,b'\x4e\x71'*4)
    uc.mem_map(0x4f800000,0x1000)
    state=list(muted); log=[]
    uc.mem_write(LATCH,bytes([1 if latched else 0])); uc.mem_write(SOLOF,bytes([solof]))
    if saved: uc.mem_write(SAVED,bytes(saved))
    sp=STACK; KIT=0x4f800000
    uc.mem_write(KIT,struct.pack('>I',KIT+0x100)); uc.mem_write(KIT+0x100+0x28,struct.pack('>I',0x4f800200))
    uc.mem_write(0x4f800200,bytes.fromhex('70014e75'))   # moveq #1,d0 ; rts  (kit bereit)
    args=[1,track,KIT]  # stack: ret, kit, track, flag
    sp-=4; uc.mem_write(sp,struct.pack('>I',1)); sp-=4; uc.mem_write(sp,struct.pack('>I',track)); sp-=4; uc.mem_write(sp,struct.pack('>I',KIT)); sp-=4; uc.mem_write(sp,struct.pack('>I',RET))
    uc.reg_write(mk.UC_M68K_REG_A7,sp)
    for r in (mk.UC_M68K_REG_D2,mk.UC_M68K_REG_D3,mk.UC_M68K_REG_D4,mk.UC_M68K_REG_A2): uc.reg_write(r,0xDEAD0000+r)
    saved_regs={r:uc.reg_read(r) for r in (mk.UC_M68K_REG_D2,mk.UC_M68K_REG_D3,mk.UC_M68K_REG_D4,mk.UC_M68K_REG_A2)}
    def rd(off): return struct.unpack('>I',uc.mem_read(uc.reg_read(mk.UC_M68K_REG_A7)+off,4))[0]
    def hook(uc,addr,size,_):
        a7=uc.reg_read(mk.UC_M68K_REG_A7)
        def ret(v=0):
            uc.reg_write(mk.UC_M68K_REG_D0,v); uc.reg_write(mk.UC_M68K_REG_PC,struct.unpack('>I',uc.mem_read(a7,4))[0]); uc.reg_write(mk.UC_M68K_REG_A7,a7+4)
        if addr==GETM: ret(state[rd(8)])
        elif addr==SETM:
            t,v,f=rd(8),rd(12),rd(16); state[t]=v; log.append(('set',t,v,f)); ret(0)
        elif addr==KEYH: ret(1 if (rd(4)==1 and func_held) else 0)
        elif addr==TOGGLE:
            log.append(('TOGGLE',rd(8))); uc.emu_stop()
    for f in (GETM,SETM,KEYH,TOGGLE): uc.hook_add(UC_HOOK_CODE,hook,begin=f,end=f)
    uc.reg_write(mk.UC_M68K_REG_PC,ENTRY)
    uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,_: uc.emu_stop(),begin=RET,end=RET)
    uc.emu_start(ENTRY,0,count=20000)
    regs_ok=all(uc.reg_read(r)==v for r,v in saved_regs.items()) if log and log[-1][0]!='TOGGLE' else None
    return state,log,uc.mem_read(SOLOF,1)[0],list(uc.mem_read(SAVED,6)),regs_ok,uc.reg_read(mk.UC_M68K_REG_A7)==STACK-12
def chk(name,cond): print(('ok  ' if cond else 'FAIL'),name); 
global_fail=[]
s,l,f,sv,rk,sp=run([0,1,0,0,1,0],True,True,2)
chk('Solo: nur Track 2 hörbar',s==[1,1,0,1,1,1]); chk('Solo-Flag=3',f==3); chk('Sicherung = alter Zustand',sv==[0,1,0,0,1,0]); chk('Register erhalten',rk); chk('Stack sauber (nur Rücksprung offen)',sp)
s2,l2,f2,sv2,rk2,_=run(s,True,True,2,solof=f,saved=sv)
chk('2. Druck stellt vorherigen Zustand wieder her',s2==[0,1,0,0,1,0] and f2==0)
s3,l3,f3,_,_,_=run([1,1,0,1,1,1],True,True,4,solof=3,saved=[0,1,0,0,1,0])
chk('Solo auf anderem Track: neue Auswahl, alte Sicherung bleibt',s3==[1,1,1,1,0,1] and f3==5)
s4,l4,f4,_,_,_=run([0,0,0,0,0,0],True,False,1)
chk('FUNC nicht gehalten -> normaler Toggle',l4==[('TOGGLE',)] or l4==[('TOGGLE',l4[0][1])] and f4==0)
s5,l5,f5,_,_,_=run([0,0,0,0,0,0],False,True,1)
chk('Nicht eingerastet (Original-Halten) -> normaler Toggle',l5 and l5[0][0]=='TOGGLE')
s6,l6,f6,_,_,_=run([1,1,0,1,1,1],True,False,2,solof=3)
chk('Normaler Druck löscht Solo-Flag',f6==0 and l6[0][0]=='TOGGLE')
