import json, struct, sys
sys.path.insert(0,'uni/bindings/python')
from unicorn import *
from unicorn import m68k_const as mk
BASE=0x40000400
img=bytearray(open('out/section_3_MAIN_OS.bin','rb').read())
for w in json.load(open('solo/63-live-mute.json'))['writes']:
    o=bytes.fromhex(w['old']); assert img[w['off']:w['off']+len(o)]==o; img[w['off']:w['off']+len(o)]=bytes.fromhex(w['new'])
FUNC=0x4005894a; RESUME=0x40058950; GETM=0x4001263c; SING=0x400cf866; KITF=0x4000eb90
STACK=0x4f000000; RET=0x4e000000
def run(muted, track, typ):
    uc=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN); uc.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
    uc.mem_map(0x40000000,0x2000000); uc.mem_write(BASE,bytes(img))
    uc.mem_map(STACK-0x10000,0x20000); uc.mem_map(RET,0x1000); uc.mem_map(0x4f800000,0x1000)
    msg=0x4f800000; uc.mem_write(msg,struct.pack('>IIII',track,60,0,typ))
    sp=STACK-4; uc.mem_write(sp,struct.pack('>I',msg)); sp-=4; uc.mem_write(sp,struct.pack('>I',RET))
    uc.reg_write(mk.UC_M68K_REG_A7,sp); uc.reg_write(mk.UC_M68K_REG_A2,0xCAFE0001)
    res={'resumed':False,'getm':None}
    def rd(off): return struct.unpack('>I',uc.mem_read(uc.reg_read(mk.UC_M68K_REG_A7)+off,4))[0]
    def ret(v):
        a7=uc.reg_read(mk.UC_M68K_REG_A7); uc.reg_write(mk.UC_M68K_REG_D0,v)
        uc.reg_write(mk.UC_M68K_REG_PC,struct.unpack('>I',uc.mem_read(a7,4))[0]); uc.reg_write(mk.UC_M68K_REG_A7,a7+4)
    def hook(uc,addr,size,_):
        if addr==SING: ret(0x1111)
        elif addr==KITF: ret(0x2222) if rd(4)==0x1111 else ret(0xBAD)
        elif addr==GETM:
            res['getm']=(rd(4),rd(8)); ret(1 if muted[rd(8)] and rd(4)==0x2222 else 0)
        elif addr==RESUME:
            res['resumed']=True; res['a2']=uc.reg_read(mk.UC_M68K_REG_A2); res['sp']=uc.reg_read(mk.UC_M68K_REG_A7); uc.emu_stop()
        elif addr==RET:
            res['returned']=True; res['a2']=uc.reg_read(mk.UC_M68K_REG_A2); res['sp']=uc.reg_read(mk.UC_M68K_REG_A7); uc.emu_stop()
    for f in (SING,KITF,GETM,RESUME,RET): uc.hook_add(UC_HOOK_CODE,hook,begin=f,end=f)
    uc.emu_start(FUNC,0,count=5000)
    return res,sp
def chk(n,c): print(('ok  ' if c else 'FAIL'),n)
M=[0,0,1,0,0,0]
r,sp=run(M,2,1); chk('Note-On auf gemutetem Track wird verworfen (kehrt zurück, nicht fortgesetzt)',r.get('returned') and not r['resumed'])
chk('  a2 und Stack wiederhergestellt',r['a2']==0xCAFE0001 and r['sp']==sp+4)
chk('  Getter bekam (Kit, Track)',r['getm']==(0x2222,2))
r,sp=run(M,3,1); chk('Note-On auf ungemutetem Track läuft normal weiter',r['resumed'])
chk('  Zustand beim Fortsetzen = Original nach den ersetzten Befehlen (a2=msg, Stack +4)',r['a2']==0x4f800000 and r['sp']==sp-4)
r,sp=run(M,2,2); chk('Note-Off auf gemutetem Track läuft weiter',r['resumed'] and r['getm'] is None)
