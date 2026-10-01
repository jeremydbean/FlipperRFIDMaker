"""Compare RFID Maker's HID raw IDs with the actual Proxmark3 C packers.
Usage: python tests/test_proxmark.py COMPILER PROXMARK3_SOURCE
Requires unicorn and pyelftools; source functions are read from the local checkout.
"""
import io
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR
from test_formats import STUB, ROOT


def function(source, name):
    start=source.index(name+'(')
    start=source.rfind('\n',0,start)+1
    brace=source.index('{',start)
    depth=1
    end=brace+1
    while depth:
        if source[end]=='{': depth+=1
        elif source[end]=='}': depth-=1
        end+=1
    return source[start:end]


def main():
    compiler=Path(sys.argv[1]).resolve()
    pm=Path(sys.argv[2]).resolve()
    os.environ['PATH']=str(compiler.parent)+os.pathsep+os.environ['PATH']
    formats=(pm/'client/src/wiegand_formats.c').read_text()
    utils=(pm/'client/src/wiegand_formatutils.c').read_text()
    harness='''
#include <string.h>
#include "wiegand_formatutils.h"
#include "parity.h"
static bool validate_card_limit(int i, wiegand_card_t* c) { (void)i; (void)c; return true; }
'''+function(utils,'add_HID_header')+'\n'+function(formats,'Pack_H10301')+'\n'+function(formats,'Pack_H10306')+'\n'+STUB+'''
unsigned match_pm(unsigned index) {
    wiegand_card_t card = {.FacilityCode=values[0],.CardNumber=values[1]};
    wiegand_message_t packed;
    bool ok=index==0 ? Pack_H10301(0,&card,&packed,true) : Pack_H10306(0,&card,&packed,true);
    uint8_t data[6], raw[5];
    const CardFormat* f=&card_formats[index];
    if(!ok || !card_encode(f,values,data,f->size) || card_proxmark_raw(f,data,f->size,raw,5)!=5) return 0;
    uint64_t result=0;
    for(unsigned i=0; i<5; ++i) result=(result<<8)|raw[i];
    return result==(((uint64_t)packed.Mid<<32)|packed.Bot) && packed.Top==0;
}
'''
    with tempfile.TemporaryDirectory(prefix='rfid-proxmark-') as folder:
        folder=Path(folder); (folder/'test.c').write_text(harness)
        path=folder/'test.elf'
        subprocess.run([str(compiler),'-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-O1','-fno-builtin','-nostdlib',
                        '-I'+str(ROOT),'-I'+str(pm/'client/src'),'-I'+str(pm/'common'),'-I'+str(pm/'include'),
                        str(folder/'test.c'),str(ROOT/'card_formats.c'),'-Wl,-Ttext=0x10000','-Wl,-e,match_pm','-o',str(path),'-lgcc'],check=True)
        elf=ELFFile(io.BytesIO(path.read_bytes()))
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        emu=Uc(UC_ARCH_ARM,UC_MODE_THUMB); emu.mem_map(0x10000,0x200000); emu.mem_map(0x400000,0x1000)
        for segment in elf.iter_segments():
            if segment['p_type']=='PT_LOAD': emu.mem_write(segment['p_vaddr'],segment.data())
        rng=random.Random(10301); count=0
        for index,fcmax in [(0,255),(17,65535)]:
            vectors=[(0,0),(fcmax,65535)] + [(rng.randrange(fcmax+1),rng.randrange(65536)) for _ in range(1000)]
            for fc,cn in vectors:
                emu.mem_write(symbols['values'],struct.pack('<5Q',fc,cn,0,0,0))
                emu.reg_write(UC_ARM_REG_SP,0x200000); emu.reg_write(UC_ARM_REG_LR,0x400001); emu.reg_write(UC_ARM_REG_R0,index)
                emu.emu_start(symbols['match_pm']|1,0x400000,count=1000000)
                assert emu.reg_read(UC_ARM_REG_R0)==1, (index,fc,cn)
                count+=1
        print(f'PASS: {count} HID H10301/H10306 raw IDs match actual Proxmark3 C packers, including HID header and parity.')

if __name__=='__main__': main()
