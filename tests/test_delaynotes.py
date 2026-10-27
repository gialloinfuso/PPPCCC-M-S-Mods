import struct, sys, json
sys.path.insert(0,'uni/bindings/python')
from unicorn import *
from unicorn import m68k_const as mk
IMG=sys.argv[1] if len(sys.argv)>1 else 'smp/stock_dn.bin'
BASE=0x40000400
img=bytes(open(IMG,'rb').read())
STACK=0x4f000000; RET=0x4e000000; TEMPO=0x40149310
SPR,TD,THIS37=0x40000e6e,0x400ddf60,0x40a725dc
def mk_uc():
    uc=Uc(UC_ARCH_M68K,UC_MODE_BIG_ENDIAN); uc.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
    uc.mem_map(0x40000000,0x2000000); uc.mem_write(BASE,img)
    uc.mem_map(STACK-0x10000,0x20000); uc.mem_map(RET,0x1000); uc.mem_map(0x4f800000,0x1000)
    return uc
R=lambda uc,r: uc.reg_read(r)
def dsp(v8_8, tempo=14400):
    uc=mk_uc(); uc.mem_write(TEMPO,struct.pack('>I',tempo))
    st=0x4f800000; uc.mem_write(st+428,struct.pack('>h',v8_8))
    sp=STACK-0x100; uc.mem_write(sp+0x24,struct.pack('>I',st))
    uc.reg_write(mk.UC_M68K_REG_A7,sp)
    for r in (mk.UC_M68K_REG_D2,mk.UC_M68K_REG_A2): uc.reg_write(r,0xC0DE0000+r)
    d2=R(uc,mk.UC_M68K_REG_D2)
    def h(uc,a,s,_): uc.emu_stop()
    uc.hook_add(UC_HOOK_CODE,h,begin=0x400581cc,end=0x400581cc)
    uc.emu_start(0x4005819a,0,count=4000)
    return R(uc,mk.UC_M68K_REG_D0)&0xffffffff, R(uc,mk.UC_M68K_REG_D2)==d2, R(uc,mk.UC_M68K_REG_A7)==sp
def fmt(this,v):
    uc=mk_uc(); res={}
    sp=STACK-0x20; buf=0x4f800100
    uc.mem_write(sp,struct.pack('>IIII',RET,this,v<<8,buf)); uc.reg_write(mk.UC_M68K_REG_A7,sp)
    uc.reg_write(mk.UC_M68K_REG_D2,0x1234); uc.reg_write(mk.UC_M68K_REG_A2,0x5678)
    def h(uc,a,s,_):
        a7=R(uc,mk.UC_M68K_REG_A7)
        rd=lambda o: struct.unpack('>I',uc.mem_read(a7+o,4))[0]
        if a==SPR:
            f=bytes(uc.mem_read(rd(8),3)); res['spr']=(rd(4)==buf, f, bytes(uc.mem_read(rd(12),5)).split(b'\0')[0].decode()); res['a7']=a7
        else: res['td']=(rd(4),rd(8),rd(12)); res['a7']=a7
        uc.emu_stop()
    for f in (SPR,TD): uc.hook_add(UC_HOOK_CODE,h,begin=f,end=f)
    uc.emu_start(0x4004dfda,0,count=4000)
    res['regs']=(R(uc,mk.UC_M68K_REG_D2)==0x1234 and R(uc,mk.UC_M68K_REG_A2)==0x5678)
    return res,sp
def chk(n,c): print(('ok  ' if c else 'FAIL'),n)
# --- DSP: 120 BPM, 750 Samples je Rasterschritt (Wert+1)
bad=[]
for v in range(128):
    d0,r1,r2=dsp(v<<8)
    exp={4:round(16/3*750),9:round(32/3*750),20:round(64/3*750),41:round(128/3*750),84:round(256/3*750)}.get(v,(v+1)*750)
    if abs(d0-exp)>12 or not r1 or not r2: bad.append((v,d0,exp,r1,r2))
chk('Delay-Laenge 0..127: nur 4,9,20,41,84 verschoben (Triolen exakt +-12 Samples), Register/Stack ok',not bad); print(bad[:5])
print('  Triolen @120 BPM:',[ (v,dsp(v<<8)[0]) for v in (4,9,20,41,84)],' Nachbarn:',[(v,dsp(v<<8)[0]) for v in (3,5,8,10,19,21)])
chk('Bruchwerte (z. B. 20,5 = 0x1480) unveraendert',dsp(0x1480)[0]==round(21.5*750))
chk('Tempo 90 BPM: 1/4T = 4/3 Schlag',abs(dsp(20<<8,tempo=10800)[0]-round(64/3*(96000*120/90)/128))<=14)
# --- Anzeige
labels={}
for v in range(128):
    r,sp=fmt(THIS37,v)
    labels[v]=r['spr'][2] if 'spr' in r else None
want={127:'1/1',63:'1/2',31:'1/4',15:'1/8',7:'/16',3:'/32',1:'/64',95:'2.',47:'4.',23:'8.',11:'16.',5:'32.',84:'1T',41:'2T',20:'4T',9:'8T',4:'16T'}
chk('Etiketten genau an den 17 Stellen',all(labels[v]==want.get(v) for v in range(128) if v in want))
others=[v for v in range(128) if v not in want]
chk('alle uebrigen 111 Werte laufen durch den Originalpfad (Anzeige Zahl)',all(fmt(THIS37,v)[0].get('td')==(0x40a70708,(v<<8)+0x100,0x4f800100) for v in others))
r,sp=fmt(THIS37,31); chk('Etikett: sprintf(buf,"%s",label) mit passendem Stack (ret,buf,fmt,arg)',r['spr'][0] and r['spr'][1]==b'%s\0' and r['a7']==sp and r['regs'])
r,sp=fmt(0x40a73398,31); chk('anderes Objekt (this): Originalpfad',r.get('td')==(0x40a70708,(31<<8)+0x100,0x4f800100))
print('  Etiketten:',{v:labels[v] for v in sorted(want)})
