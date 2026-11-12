# cfasm gegen bekannte Kodierungen (aus dem Firmware-Disassembly und aus Hand-Kodierungen der Patches)
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'solo'))
from rig import chk, done
from gen_solo import A
import cfasm
CASES = [
    ('tas 0x40192c00', '4af940192c00'), ('subx.l d4,d2', '9584'), ('mulu.l 196(a2),d1', '4c2a100000c4'),
    ('movem.l 4(sp),d2-d5/d7', '4cef00bc0004'), ('clr.b 0x40192c00', '423940192c00'),
    ('lea -12(sp),sp', '4feffff4'), ('movem.l d2/a2-a3,(sp)', '48d70c04'), ('move.l 20(sp),d2', '242f0014'),
    ('movea.l 16(sp),a2', '246f0010'), ('move.l d2,-(sp)', '2f02'), ('jsr 0x4007240c', '4eb94007240c'),
    ('addq.l #4,sp', '588f'), ('moveq #12,d1', '720c'), ('cmp.l d0,d1', 'b280'), ('move.b #1,d1', '123c0001'),
    ('addi.l #-16,d0', '0680fffffff0'), ('lea 0x400cf9a8,a3', '47f9400cf9a8'), ('jsr (a3)', '4e93'), ('clr.l -(sp)', '42a7'),
    ('movea.l (a2),a0', '2052'), ('movea.l 40(a0),a0', '20680028'), ('lea 20(sp),sp', '4fef0014'),
    ('movem.l (sp),d2/a2-a3', '4cd70c04'), ('rts', '4e75'), ('mvs.b 36(a3),d0', '712b0024'), ('mvs.w 26(a3),d0', '716b001a'),
    ('mvz.w 88(a0),d1', '73e80058'), ('mvz.b 64(a0),d1', '73a80040'), ('lea 0(a0,d0.l*4),a0', '41f00c00'),
    ('move.l (a0),592(a2)', '25500250'), ('tst.l 56(a2)', '4aaa0038'), ('move.l #0xffc00000,d1', '223cffc00000'),
    ('move.l d0,44(a2)', '2540002c'), ('lsl.l #4,d0', 'e988'), ('lsl.l d1,d0', 'e3a8'), ('asr.l #2,d0', 'e480'),
    ('lsr.l #1,d1', 'e289'), ('muls.l d1,d0', '4c010800'), ('mulu.l d1,d0', '4c010000'), ('divu.l d2,d3', '4c423003'),
    ('remu.l d1,d2:d0', '4c410002'), ('divs.l d3,d0', '4c430800'), ('btst #15,d1', '0801000f'), ('btst d7,d0', '0f00'),
    ('cmpi.l #0x7f0000,d0', '0c80007f0000'), ('swap d1', '4841'), ('ext.l d0', '48c0'), ('neg.l d0', '4480'),
    ('add.l d1,d0', 'd081'), ('sub.l d1,d0', '9081'), ('and.l d0,d1', 'c280'), ('or.l d1,d0', '8081'), ('eor.l d1,d0', 'b380'),
    ('adda.l d4,a1', 'd3c4'), ('suba.l a3,a6', '9dcb'), ('cmpa.l d7,a6', 'bdc7'), ('add.l d0,(a0)', 'd190'),
    ('move.l 0(a3,d7.l*4),-(sp)', '2f337c00'), ('pea 0x404a8cb8', '4879404a8cb8'), ('pea 2.w', '48780002'),
    ('seq d0', '57c0'), ('subq.l #1,d3', '5383'), ('tst.b d0', '4a00'), ('clr.l 40(a4)', '42ac0028'),
    ('movea.l d0,a0', '2040'), ('move.l a2,(a0)', '208a'), ('move.w d1,76(a1)', '3341004c'), ('move.b d0,124(a2)', '1540007c'),
    ('move.l 0x40a78888,d0', '203940a78888'), ('move.l d0,0x40a78888', '23c040a78888'), ('or.l d0,d1', '8280'),
    ('andi.l #0x7fff,d1', '02810000 7fff'), ('ori.l #0x8000,d1', '00810000 8000'), ('eori.l #0x7f00,d1', '0a810000 7f00'),
    ('mulu.w #100,d0', 'c0fc0064'), ('muls.w d1,d0', 'c1c1'), ('bset #3,d0', '08c00003'), ('bclr d1,d0', '0380'),
    ('move.w (a0)+,d1', '3218'), ('move.l (a3)+,-(sp)', '2f1b'), ('jmp 0x400220b2', '4ef9400220b2'), ('nop', '4e71'),
    ('extb.l d0', '49c0'), ('not.l d0', '4680'), ('cmp.b d0,d1', 'b200'), ('cmp.w d0,d1', 'b240'),
]
bad = []
for src, hx in CASES:
    a = A(0x40000000); cfasm.asm(a, src); got = cfasm.done(a).hex()
    if got != hx.replace(' ', ''): bad.append((src, got, hx))
chk('cfasm: %d Kodierungen, Abweichungen %s' % (len(CASES), bad), not bad)
a = A(0x40100000)
cfasm.asm(a, '''
start:  moveq   #3,d0
lp:     subq.l  #1,d0
        bne     lp          ; Schleife
        lea     tab,a0
        jsr     sub
        rts
sub:    rts
tab:    dc.l    start, 0x12345678
''')
c = cfasm.done(a)
chk('Labels: Bcc rueckwaerts, lea/jsr/dc.l absolut %s' % c.hex(),
    c.hex() == '7003' + '5380' + '6600fffc' + '41f9' + '40100018' + '4eb9' + '40100016' + '4e75' + '4e75' + '40100000' + '12345678')
done()
