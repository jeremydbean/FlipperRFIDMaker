"""Exercise actual ARM numeric-keypad input events for every preset's bounds.

Usage: python tests/test_decimal_input.py COMPILER SDK_HEADERS
Requires unicorn and pyelftools. Canvas/view services are mocked.
"""
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR
from test_formats import STUB

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "decimal_input.c"
#include <stdarg.h>
static DecimalModel model;
static DecimalInput widget;
uint64_t saved;
unsigned calls;
size_t strlen(const char* p) { size_t n=0; while(p[n]) ++n; return n; }
int snprintf(char* out, size_t n, const char* fmt, ...) {
    va_list ap; va_start(ap,fmt); char buffer[64]; unsigned len=0;
    if(fmt[1]=='s') {
        const char* p=va_arg(ap,const char*); while(*p && len<63) buffer[len++]=*p++;
    } else {
        uint64_t v=va_arg(ap,uint64_t); char rev[21]; unsigned count=0;
        do { rev[count++]='0'+v%10; v/=10; } while(v);
        while(count) buffer[len++]=rev[--count];
    }
    va_end(ap); for(unsigned i=0; i<len && i+1<n; ++i) out[i]=buffer[i];
    if(n) out[len<n ? len:n-1]=0; return len;
}
void* view_get_model(View* view) { (void)view; return &model; }
void view_commit_model(View* view, bool update) { (void)view; (void)update; }
static void done(void* context, uint64_t value) { (void)context; saved=value; ++calls; }
static void key(InputKey key) { InputEvent e={.key=key,.type=InputTypeShort}; decimal_event(&e,&widget); }
static void digit(char c) { model.row=(c-'0')/5; model.column=(c-'0')%5; key(InputKeyOk); }
static void save(void) { model.row=1; model.column=5; key(InputKeyOk); }
static void erase(void) { model.row=0; model.column=5; key(InputKeyOk); }
unsigned run_entry(unsigned format, unsigned field) {
    const CardField* f=&card_formats[format].fields[field]; calls=0; saved=0;
    decimal_input_configure(&widget,f->label,1,f->min,f->max,true,done,NULL);
    if(model.text[0]) return 1;
    save(); if(calls) return 2; // A blank entry is not implicitly zero or one.
    char text[21]; snprintf(text,sizeof(text),"%llu",f->max);
    for(unsigned i=0; text[i]; ++i) digit(text[i]);
    save(); if(calls!=1 || saved!=f->max) return 3;
    // Overflow must not change the valid maximum already entered.
    char before[21]; memcpy(before,model.text,sizeof(before)); digit('9');
    if(memcmp(before,model.text,sizeof(before))) return 4;
    // Existing/imported values are visible but replaced on first digit.
    decimal_input_configure(&widget,f->label,f->max,f->min,f->max,false,done,NULL);
    if(!model.text[0]) return 5;
    snprintf(text,sizeof(text),"%llu",f->min);
    for(unsigned i=0; text[i]; ++i) digit(text[i]);
    save(); if(calls!=2 || saved!=f->min) return 6;
    // Delete can empty even zero; save remains disabled until something is typed.
    for(unsigned i=0; i<21; ++i) erase();
    if(model.text[0]) return 7;
    save(); if(calls!=2) return 8;
    InputEvent back={.key=InputKeyBack,.type=InputTypeShort};
    if(decimal_event(&back,&widget) || calls!=2) return 9;
    return 0;
}
unsigned run_edit(void) {
    calls=0;
    decimal_input_configure(&widget,"Card",12345,0,65535,false,done,NULL);
    erase(); digit('9'); save(); if(saved!=12349 || calls!=1) return 1;
    decimal_input_configure(&widget,"Card",0,50,99,true,done,NULL);
    digit('9'); save(); if(calls!=1) return 2; // Prefix below min is allowed.
    digit('0'); save(); if(saved!=90 || calls!=2) return 3;
    InputEvent repeat={.key=InputKeyOk,.type=InputTypeRepeat};
    decimal_event(&repeat,&widget); if(calls!=2) return 4;
    return 0;
}
'''

def main():
    compiler, sdk = map(lambda p: Path(p).resolve(), sys.argv[1:3])
    os.environ['PATH'] = str(compiler.parent) + os.pathsep + os.environ['PATH']
    includes = [a.replace('SDK_ROOT_DIR',str(sdk)) for a in json.loads((sdk/'sdk.opts').read_text())['cc_args'].split() if a.startswith('-I')]
    with tempfile.TemporaryDirectory(prefix='rfid-keypad-') as folder:
        folder = Path(folder)
        (folder/'harness.c').write_text(HARNESS + '\n' + STUB)
        path = folder/'test.elf'
        subprocess.run([str(compiler), '-std=c11','-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-O1',
                        '-ffunction-sections','-fdata-sections','-fno-builtin','-nostdlib',
                        '-DSTM32WB','-DSTM32WB55xx','-DFURI_NDEBUG','-DNDEBUG',
                        '-I'+str(ROOT),*includes,str(folder/'harness.c'),str(ROOT/'card_formats.c'),
                        '-Wl,-Ttext=0x10000','-Wl,-e,run_entry','-Wl,--gc-sections',
                        '-Wl,--undefined=run_edit','-Wl,--undefined=info',
                        '-Wl,--unresolved-symbols=ignore-all','-o',str(path),'-lgcc'],check=True)
        elf = ELFFile(io.BytesIO(path.read_bytes()))
        symbols = {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        emu = Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        emu.mem_map(0x10000,0x200000); emu.mem_map(0x400000,0x1000)
        for segment in elf.iter_segments():
            if segment['p_type']=='PT_LOAD': emu.mem_write(segment['p_vaddr'],segment.data())
        def call(name,a=0,b=0):
            emu.reg_write(UC_ARM_REG_SP,0x200000); emu.reg_write(UC_ARM_REG_LR,0x400001)
            emu.reg_write(UC_ARM_REG_R0,a); emu.reg_write(UC_ARM_REG_R1,b)
            emu.emu_start(symbols[name]|1,0x400000,count=1000000)
            return emu.reg_read(UC_ARM_REG_R0)
        count=0
        for fmt in range(18):
            fields=call('info',fmt)>>8
            for field in range(fields):
                assert call('run_entry',fmt,field)==0, (fmt,field,'numeric event regression')
                count+=1
        assert call('run_edit')==0, 'replacement/deletion/minimum/repeat behavior'
        print(f'PASS: {count} numeric fields across 18 presets: full maxima, blank starts, replace imported values, zero, overflow, deletion, minimum prefixes, Back and repeated OK.')

if __name__=='__main__': main()
