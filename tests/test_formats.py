"""Execute the actual ARM C encoders in Unicorn, independent of Flipper hardware.

Usage: python tests/test_formats.py /path/to/arm-none-eabi-gcc
Requires: pip install unicorn pyelftools
"""
import io
import os
import pathlib
import random
import struct
import subprocess
import sys
import tempfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = pathlib.Path(__file__).resolve().parents[1]
STUB = r'''
#include "card_formats.h"
uint64_t values[5], bounds[10], parsed, decoded[5];
uint8_t output[64];
char input[256];
void* memset(void* p, int v, size_t n) {
    unsigned char* b = p; for(size_t i=0; i<n; ++i) b[i]=v; return p;
}
void* memcpy(void* p, const void* src, size_t n) {
    unsigned char* b=p; const unsigned char* a=src;
    for(size_t i=0; i<n; ++i) b[i]=a[i]; return p;
}
int memcmp(const void* p, const void* q, size_t n) {
    const unsigned char* a=p; const unsigned char* b=q;
    for(size_t i=0; i<n; ++i) if(a[i]!=b[i]) return a[i]-b[i];
    return 0;
}
unsigned info(unsigned i) {
    const CardFormat* f = &card_formats[i];
    for(unsigned j=0; j<f->count; ++j) {
        bounds[j*2]=f->fields[j].min; bounds[j*2+1]=f->fields[j].max;
        values[j]=f->fields[j].initial;
    }
    return f->size | (f->count << 8);
}
unsigned probe(unsigned i, unsigned size) {
    memset(output, 0xA5, sizeof(output));
    return card_encode(&card_formats[i], values, output, size);
}
unsigned parse_probe(void) { return card_parse_decimal(input, values[0], values[1], &parsed); }
unsigned decode_probe(unsigned i, unsigned size) {
    memset(decoded, 0xA5, sizeof(decoded));
    return card_decode(&card_formats[i], output, size, decoded);
}
'''

def bit(value, offset, width):
    return (int.from_bytes(value, 'big') >> (len(value)*8-offset-width)) & ((1 << width)-1)

def packed(parts, width):
    bits = ''.join(f'{value:0{n}b}' for value, n in parts)
    return int(bits.ljust(width*8, '0'), 2).to_bytes(width, 'big')

def wg(fc, cn):
    payload = fc*65536 + cn
    return ((payload >> 12).bit_count()%2 << 25) + payload*2 + (1-(payload & 4095).bit_count()%2)

def rev(v):
    return int(f'{v:08b}'[::-1], 2)

def reference(index, v):
    fc, cn = v[:2]
    if index == 0: return packed([(fc,8),(cn,16)],3)
    if index in (1,2,3): return packed([(v[2],16),(fc,8),(cn,16)],5)
    if index == 4:
        bits = [0]*32
        for val, locations in [(fc,[24,16,11,14,15,20,6,25]),(cn,[9,12,10,7,19,3,2,18,13,0,4,21,23,26,17,8])]:
            for pos, b in zip(locations, f'{val:0{len(locations)}b}'): bits[pos]=int(b)
        x = fc*65536 + cn
        bits[1]=(x >> 12).bit_count()%2
        bits[5]=1-(x & 4095).bit_count()%2
        checksum=sum((x >> i)&1 for i in [14,12,9,8,6,5,2,0])%2
        bits[27],bits[28]=1-checksum,checksum
        return int(''.join(map(str,bits)),2).to_bytes(4,'big')
    if index == 5: return packed([(fc,8),(v[2],8),(cn,16)],4)
    if index == 6: return packed([(26,8),(wg(fc,cn),26)],9)
    if index == 7: return packed([(26,8),(fc,8),(cn,16)],4)
    if index == 8: return packed([(v[2],4),(v[3],4),(fc,24),(cn,32)],8)
    if index == 9:
        value = 0x80000000
        # Original card bit positions for each logical FC / CN bit (low to high).
        fc_pos=[13,30,18,22,24]
        cn_pos=[14,21,26,28,20,7,9,15,12,29,16,19,5,4,27,17,8,11,23,25,6,10]
        for val,positions in [(fc,fc_pos),(cn,cn_pos)]:
            for i,pos in enumerate(positions): value |= ((val>>i)&1)<<pos
        return value.to_bytes(4,'big')
    if index == 10: return packed([(fc,16),(cn,16),(v[2],8),(v[3],8)],6)
    if index in (11,12): return fc.to_bytes(4,'big')
    if index == 13: return fc.to_bytes(5,'big')
    if index == 14: return packed([(cn,32),(fc,32)],8)
    if index == 15:
        bits = '0000' + ''.join('10' if b=='1' else '01' for b in f'{fc*65536+cn:034b}')
        # Reflected CRC-8, polynomial 0x8C, final XOR 0x06.
        crc = 0
        for b in int(bits,2).to_bytes(9,'big'):
            crc ^= b
            for _ in range(8): crc = (crc>>1) ^ (0x8C if crc&1 else 0)
        return packed([(0,10),(fc,8),(cn,16),(crc^6,8),(0,6)],6)
    if index == 16:
        plain = packed([(0x90,8),(26,6),(3,2),(v[2],16),(wg(fc,cn),26),(0,14)],9)
        wire = '111110'
        for i,b in enumerate(plain):
            b = rev(b ^ (0x90 if i else 0))
            wire += f'{b>>4:04b}0{b&15:04b}0'
        return int(wire,2).to_bytes(12,'big')
    if index == 17:
        payload=fc*65536+cn
        return packed([(1,7),(0,2),(1,1),((payload>>16).bit_count()%2,1),(payload,32),(1-(payload&65535).bit_count()%2,1)],6)
    raise AssertionError(index)

def main():
    compiler = str(pathlib.Path(sys.argv[1]).resolve())
    os.environ['PATH'] = str(pathlib.Path(compiler).parent) + os.pathsep + os.environ['PATH']
    with tempfile.TemporaryDirectory(prefix='rfid-maker-test-', dir=sys.argv[2] if len(sys.argv)>2 else None) as folder:
        folder=pathlib.Path(folder)
        (folder/'stub.c').write_text(STUB)
        elf_path=folder/'test.elf'
        subprocess.run([compiler,'-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-O1','-fno-builtin','-nostdlib',
                        '-I'+str(ROOT),str(ROOT/'card_formats.c'),str(folder/'stub.c'),
                        '-Wl,-Ttext=0x10000','-Wl,-e,probe','-o',str(elf_path),'-lgcc'],check=True)
        elf=ELFFile(io.BytesIO(elf_path.read_bytes()))
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        emu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        emu.mem_map(0x10000,0x200000)
        emu.mem_map(0x400000,0x1000)
        for segment in elf.iter_segments():
            if segment['p_type']=='PT_LOAD': emu.mem_write(segment['p_vaddr'],segment.data())
        def call(name, a=0, b=0):
            emu.reg_write(UC_ARM_REG_SP,0x200000)
            emu.reg_write(UC_ARM_REG_LR,0x400001)
            emu.reg_write(UC_ARM_REG_R0,a); emu.reg_write(UC_ARM_REG_R1,b)
            emu.emu_start(symbols[name]|1,0x400000,count=1000000)
            return emu.reg_read(UC_ARM_REG_R0)
        rng=random.Random(1234)
        cases=0
        for index in range(18):
            metadata=call('info',index)
            size,count=metadata&255,metadata>>8
            bounds=struct.unpack('<10Q',emu.mem_read(symbols['bounds'],80))
            limits=[(bounds[j*2],bounds[j*2+1]) for j in range(count)]
            vectors=[[lo for lo,hi in limits],[hi for lo,hi in limits]]
            vectors += [[rng.randint(lo,hi) for lo,hi in limits] for _ in range(100)]
            for values in vectors:
                values += [0]*(5-len(values))
                emu.mem_write(symbols['values'],struct.pack('<5Q',*values))
                assert call('probe',index,size)==1, (index,values)
                actual=bytes(emu.mem_read(symbols['output'],64))
                assert actual[:size]==reference(index,values), (index,values,actual[:size].hex(),reference(index,values).hex())
                assert actual[size:]==b'\xa5'*(64-size), 'buffer overrun'
                assert call('decode_probe',index,size)==1, ('decode',index,values)
                decoded=struct.unpack('<5Q',emu.mem_read(symbols['decoded'],40))
                assert list(decoded[:count])==values[:count], ('decode fields',index,decoded,values)
                assert bytes(emu.mem_read(symbols['decoded']+count*8,40-count*8))==b'\xa5'*(40-count*8), 'decoder output overrun'
                cases+=1
            assert call('probe',index,size-1)==0, 'incorrect size accepted'
            assert call('decode_probe',index,size-1)==0, 'incorrect decode size accepted'
            for field,(lo,hi) in enumerate(limits):
                invalid=[low for low,high in limits]+[0]*(5-count)
                invalid[field]=hi+1
                emu.mem_write(symbols['values'],struct.pack('<5Q',*invalid))
                assert call('probe',index,size)==0, 'out-of-range field accepted'
            # Unknown bits/layouts must either decode losslessly or remain raw.
            for _ in range(25):
                raw=bytes(rng.getrandbits(8) for _ in range(size))
                emu.mem_write(symbols['output'],raw)
                if call('decode_probe',index,size):
                    decoded=bytes(emu.mem_read(symbols['decoded'],40))
                    emu.mem_write(symbols['values'],decoded)
                    assert call('probe',index,size)==1
                    assert bytes(emu.mem_read(symbols['output'],size))==raw, 'decoder discarded unknown bits'
                else:
                    assert bytes(emu.mem_read(symbols['decoded'],40))==b'\xa5'*40, 'failed decode changed fields'
        parser_cases=[('',0,255,False),('150',0,255,True),('256',0,255,False),('-1',0,255,False),
                      ('1.5',0,255,False),('0x96',0,255,False),(' 150',0,255,False),('150x',0,255,False),
                      ('0',1,255,False),('255',1,255,True),('00001',0,255,True),
                      ('18446744073709551615',0,2**64-1,True),('18446744073709551616',0,2**64-1,False)]
        for text,lo,hi,valid in parser_cases:
            emu.mem_write(symbols['input'],text.encode()+b'\0')
            emu.mem_write(symbols['values'],struct.pack('<5Q',lo,hi,0,0,0))
            assert bool(call('parse_probe'))==valid, ('parser',text)
            if valid: assert struct.unpack('<Q',emu.mem_read(symbols['parsed'],8))[0]==int(text)
        print(f'PASS: {cases} ARM encode/decode vectors across 18 presets; 450 arbitrary payload preservation checks; field limits, buffer bounds, and {len(parser_cases)} parser cases.')

if __name__=='__main__': main()
