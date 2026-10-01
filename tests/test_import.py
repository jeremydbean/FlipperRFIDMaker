"""Run the app's actual import controller in ARM emulation with mocked SDK services.

Usage: python tests/test_import.py COMPILER SDK_HEADERS [PRIVATE_SAMPLE.rfid]
The optional file is read locally and is never copied into the repository.
Requires unicorn and pyelftools. Hardware/browser interactions are mocked.
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
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR
from test_formats import STUB, reference

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "rfid_maker.c"
struct FuriString { char text[512]; };
static struct FuriString strings[8];
static unsigned allocated, mode, running, dialog_calls, pending, in_input, bad_callback;
static unsigned blink_starts, blink_stops, worker_starts, worker_stops, emulation_starts, thread_stops;
static unsigned led[3], notification_calls;
const NotificationMessage message_blink_stop = {.type=NotificationMessageTypeLedBlinkStop};
const NotificationMessage message_red_255 = {.type=NotificationMessageTypeLedRed,.data.led.value=255};
const NotificationMessage message_green_0 = {.type=NotificationMessageTypeLedGreen,.data.led.value=0};
const NotificationMessage message_blue_255 = {.type=NotificationMessageTypeLedBlue,.data.led.value=255};
const NotificationMessage message_red_0 = {.type=NotificationMessageTypeLedRed,.data.led.value=0};
const NotificationMessage message_blue_0 = {.type=NotificationMessageTypeLedBlue,.data.led.value=0};
const NotificationMessage message_do_not_reset = {.type=NotificationMessageTypeDoNotReset};
uint8_t fixture[9];
uint32_t state[10];

size_t strlen(const char* p) { size_t n=0; while(p[n]) ++n; return n; }
int strcmp(const char* a, const char* b) {
    while(*a && *a==*b) { ++a; ++b; } return (unsigned char)*a-(unsigned char)*b;
}
FuriString* furi_string_alloc(void) {
    FuriString* s=&strings[allocated++]; s->text[0]=0; return s;
}
void furi_string_free(FuriString* s) { (void)s; }
void furi_string_set_str(FuriString* s, const char* p) {
    unsigned i=0; for(; p[i] && i<511; ++i) s->text[i]=p[i]; s->text[i]=0;
}
void (furi_string_set)(FuriString* s, FuriString* p) { furi_string_set_str(s,p->text); }
void furi_string_reset(FuriString* s) { s->text[0]=0; }
bool furi_string_empty(const FuriString* s) { return !s->text[0]; }
const char* furi_string_get_cstr(const FuriString* s) { return s->text; }
int furi_string_printf(FuriString* s, const char* format, ...) {
    furi_string_set_str(s,format); return strlen(format);
}
int snprintf(char* s, size_t n, const char* format, ...) {
    (void)format; if(n) s[0]=0; return 0;
}
void dialog_file_browser_set_basic_options(DialogsFileBrowserOptions* o, const char* ext, const Icon* icon) {
    memset(o,0,sizeof(*o)); o->extension=ext; o->icon=icon;
}
bool dialog_file_browser_show(DialogsApp* d, FuriString* selected, FuriString* path, const DialogsFileBrowserOptions* options) {
    (void)d; (void)path; (void)options;
    ++dialog_calls; if(in_input) bad_callback=1;
    if(mode==1) return false;
    furi_string_set_str(selected,"/ext/lfrfid/fixture.rfid"); return true;
}
ProtocolId lfrfid_dict_file_load(ProtocolDict* d, const char* path) {
    (void)d; (void)path; return mode==2 ? PROTOCOL_NO : LFRFIDProtocolAwid;
}
size_t protocol_dict_get_data_size(ProtocolDict* d, size_t id) { (void)d; (void)id; return 9; }
void protocol_dict_get_data(ProtocolDict* d, size_t id, uint8_t* out, size_t n) {
    (void)d; (void)id; memcpy(out,fixture,n); if(mode==3) out[0]=34;
}
const char* protocol_dict_get_name(ProtocolDict* d, size_t id) { (void)d; (void)id; return "AWID"; }
ProtocolId protocol_dict_get_protocol_by_name(ProtocolDict* d, const char* name) {
    (void)d; return strcmp(name,"AWID")==0 ? LFRFIDProtocolAwid : PROTOCOL_NO;
}
void submenu_reset(Submenu* s) { (void)s; }
void submenu_set_header(Submenu* s, const char* text) { (void)s; (void)text; }
void submenu_add_item(Submenu* s, const char* label, uint32_t id, SubmenuItemCallback cb, void* context) {
    (void)s; (void)label; (void)id; (void)cb; (void)context;
}
void text_box_reset(TextBox* b) { (void)b; }
void text_box_set_text(TextBox* b, const char* text) { (void)b; (void)text; }
void text_box_set_font(TextBox* b, TextBoxFont font) { (void)b; (void)font; }
void view_dispatcher_switch_to_view(ViewDispatcher* d, uint32_t id) {
    (void)d; if(id==VIEW_NONE) running=0;
}
void view_dispatcher_send_custom_event(ViewDispatcher* d, uint32_t event) { (void)d; pending=event; }
void view_dispatcher_stop(ViewDispatcher* d) { (void)d; running=0; }
void notification_message(NotificationApp* n, const NotificationSequence* sequence) {
    (void)n;
    ++notification_calls;
    if(sequence==&rfid_led_on) ++blink_starts;
    if(sequence==&rfid_led_release) ++blink_stops;
    bool reset=true;
    for(unsigned i=0; (*sequence)[i]; ++i) {
        const NotificationMessage* m=(*sequence)[i];
        if(m->type==NotificationMessageTypeLedRed) led[0]=m->data.led.value;
        if(m->type==NotificationMessageTypeLedGreen) led[1]=m->data.led.value;
        if(m->type==NotificationMessageTypeLedBlue) led[2]=m->data.led.value;
        if(m->type==NotificationMessageTypeDoNotReset) reset=false;
    }
    // Firmware releases the notification layer to the internal charging layer.
    if(reset) { led[0]=0; led[1]=255; led[2]=0; }
}
void notification_message_block(NotificationApp* n, const NotificationSequence* sequence) {
    notification_message(n,sequence);
}
void lfrfid_worker_start_thread(LFRFIDWorker* w) { (void)w; ++worker_starts; }
void lfrfid_worker_emulate_start(LFRFIDWorker* w, LFRFIDProtocol protocol) {
    (void)w; if(protocol==LFRFIDProtocolAwid) ++emulation_starts;
}
void lfrfid_worker_stop(LFRFIDWorker* w) { (void)w; ++worker_stops; }
void lfrfid_worker_stop_thread(LFRFIDWorker* w) { (void)w; ++thread_stops; }
void protocol_dict_set_data(ProtocolDict* d, size_t id, const uint8_t* data, size_t n) {
    (void)d; (void)id; (void)data; (void)n;
}

unsigned test_emulation(void) {
    allocated=0; running=1; notification_calls=0;
    led[0]=0; led[1]=255; led[2]=0; // USB charging indicator.
    blink_starts=blink_stops=worker_starts=worker_stops=emulation_starts=thread_stops=0;
    Maker app; memset(&app,0,sizeof(app));
    uint8_t data[64]; app.data=data; app.capacity=sizeof(data);
    app.page=PageForm; app.protocol=LFRFIDProtocolAwid; app.size=9;
    app.format=&card_formats[6]; app.values[0]=5; app.values[1]=1234;
    app.display=furi_string_alloc(); app.source_path=furi_string_alloc();
    menu_callback(&app,ActionEmulate);
    if(!app.emulating || !app.blink_on || app.page!=PageEmulate || blink_starts!=1 || blink_stops ||
       worker_starts!=1 || emulation_starts!=1 || led[0]!=255 || led[1]!=0 || led[2]!=255) return 0;
    tick_callback(&app);
    if(app.blink_on || led[0] || led[1] || led[2]) return 0;
    tick_callback(&app);
    if(!app.blink_on || led[0]!=255 || led[1]!=0 || led[2]!=255) return 0;
    back_callback(&app);
    if(app.emulating || app.blink_on || app.page!=PageForm || blink_stops!=1 || worker_stops!=1 ||
       thread_stops!=1 || led[0] || led[1]!=255 || led[2]) return 0;
    unsigned calls=notification_calls;
    tick_callback(&app);
    stop_emulating(&app);
    if(notification_calls!=calls || blink_stops!=1 || worker_stops!=1 || thread_stops!=1) return 0;
    menu_callback(&app,ActionEmulate);
    stop_emulating(&app); // Same cleanup invoked when the app exits.
    return !app.emulating && blink_starts==3 && blink_stops==2 && worker_starts==2 &&
           worker_stops==2 && emulation_starts==2 && thread_stops==2 &&
           led[0]==0 && led[1]==255 && led[2]==0;
}

unsigned test_open(unsigned test_mode) {
    allocated=0; mode=test_mode; running=1; pending=0;
    dialog_calls=0; bad_callback=0;
    Maker app; memset(&app,0,sizeof(app));
    uint8_t data[64]; app.data=data; app.capacity=sizeof(data);
    app.page=PageTypes;
    app.display=furi_string_alloc(); app.source_path=furi_string_alloc(); app.browse_path=furi_string_alloc();
    in_input=1; menu_callback(&app,ActionOpen); in_input=0;
    unsigned deferred=pending==EventOpen && dialog_calls==0;
    custom_callback(&app,pending);
    state[0]=running; state[1]=deferred; state[2]=bad_callback; state[3]=dialog_calls;
    state[4]=app.page;
    state[5]=app.format ? (unsigned)(app.format-card_formats) : 999;
    state[6]=app.values[0]; state[7]=app.values[1];
    state[8]=!furi_string_empty(app.source_path);
    state[9]=memcmp(app.data,fixture,9)==0;
    if(mode==2) { back_callback(&app); state[4]=app.page; state[0]=running; }
    return 1;
}
'''

def main():
    compiler = Path(sys.argv[1]).resolve()
    sdk = Path(sys.argv[2]).resolve()
    os.environ['PATH']=str(compiler.parent)+os.pathsep+os.environ['PATH']
    includes = [arg.replace('SDK_ROOT_DIR',str(sdk)) for arg in json.loads((sdk/'sdk.opts').read_text())['cc_args'].split() if arg.startswith('-I')]
    data = reference(6,[5,1234,0,0,0])
    expected=(5,1234)
    if len(sys.argv)>3:
        sample=Path(sys.argv[3])
        original=sample.read_bytes()
        fields=dict(line.split(':',1) for line in original.decode('utf-8-sig').splitlines() if ':' in line)
        assert fields['Filetype'].strip()=='Flipper RFID key' and fields['Version'].strip()=='1'
        assert fields['Key type'].strip()=='AWID', 'This regression fixture expects AWID'
        data=bytes.fromhex(fields['Data'])
        assert len(data)==9
        bits=''.join(f'{b:08b}' for b in data)
        expected=(int(bits[9:17],2),int(bits[17:33],2))
    with tempfile.TemporaryDirectory(prefix='rfid-import-') as folder:
        folder=Path(folder)
        (folder/'harness.c').write_text(HARNESS+'\n'+STUB)
        elf_path=folder/'test.elf'
        subprocess.run([str(compiler),'-std=c11','-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-O1',
                        '-ffunction-sections','-fdata-sections','-fno-builtin','-nostdlib',
                        '-DSTM32WB','-DSTM32WB55xx','-DFURI_NDEBUG','-DNDEBUG',
                        '-I'+str(ROOT),*includes,str(folder/'harness.c'),str(ROOT/'card_formats.c'),
                        '-Wl,-Ttext=0x10000','-Wl,-e,test_open','-Wl,--gc-sections','-Wl,--undefined=test_emulation',
                        '-Wl,--unresolved-symbols=ignore-all','-o',str(elf_path),'-lgcc'],check=True)
        elf=ELFFile(io.BytesIO(elf_path.read_bytes()))
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        emu=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        emu.mem_map(0x10000,0x200000); emu.mem_map(0x400000,0x1000)
        for segment in elf.iter_segments():
            if segment['p_type']=='PT_LOAD': emu.mem_write(segment['p_vaddr'],segment.data())
        emu.mem_write(symbols['fixture'],data)
        for mode in range(4):
            emu.reg_write(UC_ARM_REG_SP,0x200000); emu.reg_write(UC_ARM_REG_LR,0x400001)
            emu.reg_write(UC_ARM_REG_R0,mode)
            emu.emu_start(symbols['test_open']|1,0x400000,count=1000000)
            s=struct.unpack('<10I',emu.mem_read(symbols['state'],40))
            assert s[:4]==(1,1,0,1), ('event loop/browser callback',mode,s)
            if mode==0:
                assert s[4:]==(1,6,*expected,1,1), ('AWID form',s)
            elif mode in (1,2):
                assert s[4]==0 and s[8]==0, ('cancel/error recovery',s)
            else:
                assert s[4]==5 and s[5]==999 and s[8]==1, ('unknown format raw fallback',s)
        emu.reg_write(UC_ARM_REG_SP,0x200000); emu.reg_write(UC_ARM_REG_LR,0x400001)
        emu.emu_start(symbols['test_emulation']|1,0x400000,count=1000000)
        assert emu.reg_read(UC_ARM_REG_R0)==1, 'emulation LED/worker lifecycle failed'
        if len(sys.argv)>3: assert sample.read_bytes()==original
        print('PASS: actual ARM import and emulation controllers: valid AWID, cancel/error/raw fallback; dispatcher stays running; magenta/off ticks override USB green; Back restores charging green; worker start/stop/restart/cleanup lifecycle.')

if __name__=='__main__': main()
