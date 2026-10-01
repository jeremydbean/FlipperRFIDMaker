// SPDX-License-Identifier: GPL-3.0-or-later
#include "card_formats.h"
#include <dialogs/dialogs.h>
#include <furi.h>
#include <gui/gui.h>
#include <gui/modules/byte_input.h>
#include <gui/modules/number_input.h>
#include <gui/modules/submenu.h>
#include <gui/modules/text_box.h>
#include <gui/modules/text_input.h>
#include <gui/view_dispatcher.h>
#include <lfrfid/lfrfid_dict_file.h>
#include <lfrfid/lfrfid_worker.h>
#include <lfrfid/protocols/lfrfid_protocols.h>
#include <notification/notification.h>
#include <notification/notification_messages.h>
#include <stdio.h>
#include <storage/storage.h>
#include <string.h>

enum { ViewMenu, ViewInput, ViewText, ViewBytes, ViewNumber };
enum {
    EventInput = 1000,
    EventBytes,
    EventNumber,
    ActionPreview = 100,
    ActionSave,
    ActionEmulate,
    ActionRaw,
    ActionEditRaw,
    ActionOpen,
    ActionAbout,
    EventOpen = 1100
};
typedef enum {
    PageTypes,
    PageForm,
    PageField,
    PageHex,
    PageName,
    PageStatus,
    PageEmulate,
    PageRawTypes,
    PageBytes,
    PageLoadError,
    PageAbout
} Page;
typedef struct {
    Gui *gui;
    Storage *storage;
    DialogsApp *dialogs;
    NotificationApp *notifications;
    ViewDispatcher *dispatcher;
    Submenu *menu;
    TextInput *input;
    TextBox *text;
    ByteInput *bytes;
    NumberInput *number;
    ProtocolDict *dict;
    LFRFIDWorker *worker;
    FuriString *display;
    FuriString *source_path;
    FuriString *browse_path;
    const CardFormat *format;
    ProtocolId protocol;
    uint64_t values[CARD_MAX_FIELDS];
    uint8_t *data;
    size_t size;
    size_t capacity;
    size_t field;
    char buffer[40];
    char header[64];
    Page page;
    bool emulating;
    bool blink_on;
    uint8_t blink_ticks;
} Maker;

// Own all three notification LED channels while emulating, so an underlying
// charging/status green does not mask the pulse. Release them when finished.
static const NotificationSequence rfid_led_on = {
    &message_blink_stop, &message_red_255,      &message_green_0,
    &message_blue_255,   &message_do_not_reset, NULL,
};
static const NotificationSequence rfid_led_off = {
    &message_red_0, &message_green_0, &message_blue_0, &message_do_not_reset, NULL,
};
static const NotificationSequence rfid_led_release = {
    &message_blink_stop, &message_red_0, &message_green_0, &message_blue_0, NULL,
};

static void show_types(Maker *app);
static void show_form(Maker *app);
static void show_raw_types(Maker *app);

static void open_card(Maker *app) {
    DialogsFileBrowserOptions options;
    dialog_file_browser_set_basic_options(&options, ".rfid", NULL);
    options.base_path = STORAGE_EXT_PATH_PREFIX;
    FuriString *selected = furi_string_alloc();
    bool chosen = dialog_file_browser_show(app->dialogs, selected, app->browse_path, &options);
    if(!chosen) {
        furi_string_free(selected);
        show_types(app);
        return;
    }
    furi_string_set(app->browse_path, selected);
    ProtocolId protocol = lfrfid_dict_file_load(app->dict, furi_string_get_cstr(selected));
    if(protocol == PROTOCOL_NO) {
        furi_string_printf(app->display,
                           "Cannot open RFID file\n\n%s\n\nFile may be damaged or its type "
                           "unsupported by this SDK.\nBack: type menu",
                           furi_string_get_cstr(selected));
        furi_string_free(selected);
        // Show a load error without entering a form for an invalid protocol.
        app->page = PageLoadError;
        text_box_reset(app->text);
        text_box_set_text(app->text, furi_string_get_cstr(app->display));
        view_dispatcher_switch_to_view(app->dispatcher, ViewText);
        return;
    }
    app->protocol = protocol;
    app->size = protocol_dict_get_data_size(app->dict, protocol);
    protocol_dict_get_data(app->dict, protocol, app->data, app->size);
    furi_string_set(app->source_path, selected);
    furi_string_free(selected);
    app->format = NULL;
    const char *name = protocol_dict_get_name(app->dict, protocol);
    for(size_t i = 0; i < card_format_count; ++i) {
        if(strcmp(card_formats[i].protocol, name) == 0 &&
           card_decode(&card_formats[i], app->data, app->size, app->values)) {
            app->format = &card_formats[i];
            break;
        }
    }
    show_form(app);
    if(!app->format) {
        furi_string_printf(
            app->display,
            "Opened: %s\n\nThis layout has no lossless decimal form. Original protocol data is "
            "preserved for HEX editing and Save as.\n\nBack: edit file",
            name);
        app->page = PageStatus;
        text_box_reset(app->text);
        text_box_set_text(app->text, furi_string_get_cstr(app->display));
        view_dispatcher_switch_to_view(app->dispatcher, ViewText);
    }
}

static void stop_emulating(Maker *app) {
    if(app->emulating) {
        app->emulating = false;
        app->blink_on = false;
        app->blink_ticks = 0;
        // Wait for app-owned sequences to finish before the FAP can unload.
        notification_message_block(app->notifications, &rfid_led_release);
        lfrfid_worker_stop(app->worker);
        lfrfid_worker_stop_thread(app->worker);
    }
}
static void show_text(Maker *app, Page page) {
    app->page = page;
    text_box_reset(app->text);
    text_box_set_font(app->text, TextBoxFontText);
    text_box_set_text(app->text, furi_string_get_cstr(app->display));
    view_dispatcher_switch_to_view(app->dispatcher, ViewText);
}
static bool prepare(Maker *app) {
    if(app->format && !card_encode(app->format, app->values, app->data, app->size)) {
        furi_string_set(app->display, "Cannot encode this format.\nValues or SDK layout mismatch.");
        show_text(app, PageStatus);
        return false;
    }
    protocol_dict_set_data(app->dict, app->protocol, app->data, app->size);
    return true;
}
static void preview(Maker *app) {
    if(!prepare(app))
        return;
    furi_string_printf(app->display, "%s\n\nHEX (.rfid Data):\n",
                       protocol_dict_get_name(app->dict, app->protocol));
    for(size_t i = 0; i < app->size; ++i) {
        furi_string_cat_printf(app->display, "%02X%s", app->data[i],
                               ((i + 1) % 8 == 0) ? "\n" : " ");
    }
    uint8_t raw[12];
    size_t raw_size = card_proxmark_raw(app->format, app->data, app->size, raw, sizeof(raw));
    if(raw_size) {
        furi_string_cat(app->display, app->format->encoding == CardEm
                                          ? "\n\nProxmark ID (EM410x):\n"
                                          : "\n\nProxmark raw HEX:\n");
        for(size_t i = 0; i < raw_size; ++i)
            furi_string_cat_printf(app->display, "%02X", raw[i]);
        if(app->format->encoding == CardHid26) {
            uint64_t sheet = 0;
            for(size_t i = 0; i < raw_size; ++i)
                sheet = (sheet << 8) | raw[i];
            sheet &= ~(UINT64_C(1) << 26);
            furi_string_cat_printf(
                app->display,
                "\n\nSheet-style HEX:\n%010llX\n"
                "Omits the HID format marker. Use Proxmark raw HEX above for the complete ID.",
                sheet);
        }
    } else {
        furi_string_cat(app->display, "\n\nProxmark raw HEX:\nNot implemented for this layout.");
    }
    furi_string_cat(app->display, "\n\nFirmware interpretation:\n");
    if(!furi_string_empty(app->source_path))
        furi_string_cat_printf(app->display, "Source: %s\n\n",
                               furi_string_get_cstr(app->source_path));
    FuriString *details = furi_string_alloc();
    protocol_dict_render_data(app->dict, details, app->protocol);
    furi_string_cat(app->display, details);
    furi_string_free(details);
    if(app->format)
        furi_string_cat_printf(app->display, "\n\n%s", app->format->note);
    else
        furi_string_cat(
            app->display,
            "\n\nRaw protocol data. A valid byte count does not guarantee a valid credential.");
    furi_string_cat(app->display, "\n\nBack: return to fields");
    show_text(app, PageHex);
}
static void input_done(void *context) {
    Maker *app = context;
    view_dispatcher_send_custom_event(app->dispatcher, EventInput);
}
static void bytes_done(void *context) {
    Maker *app = context;
    view_dispatcher_send_custom_event(app->dispatcher, EventBytes);
}
static void number_done(void *context, int32_t value) {
    Maker *app = context;
    app->values[app->field] = (uint64_t)value;
    view_dispatcher_send_custom_event(app->dispatcher, EventNumber);
}
static bool input_validator(const char *text, FuriString *error, void *context) {
    Maker *app = context;
    if(app->page == PageField) {
        const CardField *field = &app->format->fields[app->field];
        uint64_t n;
        if(card_parse_decimal(text, field->min, field->max, &n))
            return true;
        furi_string_printf(error, "Decimal only\n%llu to %llu", field->min, field->max);
        return false;
    }
    if(!*text) {
        furi_string_set(error, "Enter a file name");
        return false;
    }
    for(const char *p = text; *p; ++p) {
        if(!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') ||
             *p == '_' || *p == '-')) {
            furi_string_set(error, "Use letters, numbers,\nunderscore or hyphen");
            return false;
        }
    }
    FuriString *path = furi_string_alloc_printf(STORAGE_EXT_PATH_PREFIX "/lfrfid/%s.rfid", text);
    bool exists = storage_common_stat(app->storage, furi_string_get_cstr(path), NULL) == FSE_OK;
    furi_string_free(path);
    if(exists) {
        furi_string_set(error, "Name already exists.\nChoose another name.");
        return false;
    }
    return true;
}
static void edit_field(Maker *app, size_t field) {
    app->field = field;
    app->page = PageField;
    snprintf(app->buffer, sizeof(app->buffer), "%llu", app->values[field]);
    snprintf(app->header, sizeof(app->header), "%s (decimal)", app->format->fields[field].label);
    const CardField *limits = &app->format->fields[field];
    if(limits->max <= INT32_MAX) {
        number_input_set_header_text(app->number, app->header);
        number_input_set_result_callback(app->number, number_done, app, app->values[field],
                                         limits->min, limits->max);
        view_dispatcher_switch_to_view(app->dispatcher, ViewNumber);
        return;
    }
    text_input_reset(app->input);
    text_input_set_header_text(app->input, app->header);
    text_input_set_result_callback(app->input, input_done, app, app->buffer, 21, true);
    text_input_set_validator(app->input, input_validator, app);
    view_dispatcher_switch_to_view(app->dispatcher, ViewInput);
}
static void edit_bytes(Maker *app) {
    app->page = PageBytes;
    byte_input_set_header_text(app->bytes, "Protocol data (HEX)");
    byte_input_set_result_callback(app->bytes, bytes_done, NULL, app, app->data, app->size);
    view_dispatcher_switch_to_view(app->dispatcher, ViewBytes);
}
static void begin_save(Maker *app) {
    if(!prepare(app))
        return;
    app->page = PageName;
    snprintf(app->buffer, sizeof(app->buffer), "card");
    if(!furi_string_empty(app->source_path)) {
        const char *path = furi_string_get_cstr(app->source_path);
        const char *base = strrchr(path, '/');
        base = base ? base + 1 : path;
        size_t length = strlen(base);
        if(length >= 5)
            length -= 5; // Native browser filters the .rfid extension.
        if(length > 27)
            length = 27;
        for(size_t i = 0; i < length; ++i) {
            char c = base[i];
            app->buffer[i] = ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                              (c >= '0' && c <= '9') || c == '_' || c == '-')
                                 ? c
                                 : '_';
        }
        snprintf(app->buffer + length, sizeof(app->buffer) - length, "_copy");
    }
    text_input_reset(app->input);
    text_input_set_header_text(app->input, "File name (without .rfid)");
    text_input_set_result_callback(app->input, input_done, app, app->buffer, 33, true);
    text_input_set_validator(app->input, input_validator, app);
    view_dispatcher_switch_to_view(app->dispatcher, ViewInput);
}
static void save_card(Maker *app) {
    FuriString *error = furi_string_alloc();
    if(!input_validator(app->buffer, error, app)) {
        furi_string_set(app->display, error);
        furi_string_free(error);
        show_text(app, PageStatus);
        return;
    }
    furi_string_free(error);
    FuriString *path =
        furi_string_alloc_printf(STORAGE_EXT_PATH_PREFIX "/lfrfid/%s.rfid", app->buffer);
    FS_Error mkdir_result = storage_common_mkdir(app->storage, STORAGE_EXT_PATH_PREFIX "/lfrfid");
    bool saved = (mkdir_result == FSE_OK || mkdir_result == FSE_EXIST) &&
                 lfrfid_dict_file_save(app->dict, app->protocol, furi_string_get_cstr(path));
    furi_string_printf(app->display,
                       saved
                           ? "Saved\n\n%s\n\nOpen from the RFID app.\nBack: return to fields"
                           : "Save failed\n\nCheck SD card and free space.\nBack: return to fields",
                       furi_string_get_cstr(path));
    furi_string_free(path);
    show_text(app, PageStatus);
}
static void menu_callback(void *context, uint32_t index) {
    Maker *app = context;
    if(app->page == PageTypes) {
        if(index == ActionOpen) {
            // Open dialogs after the input callback has returned. VIEW_NONE would
            // stop the dispatcher; the dialog service manages its own view.
            view_dispatcher_send_custom_event(app->dispatcher, EventOpen);
            return;
        }
        if(index == ActionAbout) {
            furi_string_set(app->display,
                            "RFID Maker v0.8\n\nCreated by: KindaCharming\n\n"
                            "Create and edit 125 kHz RFID files using decimal values.\n\n"
                            "GPL-3.0-or-later\n\nBack: type menu");
            show_text(app, PageAbout);
            return;
        }
        if(index == ActionRaw) {
            show_raw_types(app);
            return;
        }
        app->format = &card_formats[index];
        furi_string_reset(app->source_path);
        app->protocol = protocol_dict_get_protocol_by_name(app->dict, app->format->protocol);
        app->size = protocol_dict_get_data_size(app->dict, app->protocol);
        for(size_t i = 0; i < app->format->count; ++i)
            app->values[i] = app->format->fields[i].initial;
        show_form(app);
    } else if(app->page == PageRawTypes) {
        app->format = NULL;
        furi_string_reset(app->source_path);
        app->protocol = index;
        app->size = protocol_dict_get_data_size(app->dict, app->protocol);
        memset(app->data, 0, app->capacity);
        show_form(app);
    } else if(app->page == PageForm) {
        if(index < CARD_MAX_FIELDS)
            edit_field(app, index);
        else if(index == ActionPreview)
            preview(app);
        else if(index == ActionSave)
            begin_save(app);
        else if(index == ActionEditRaw)
            edit_bytes(app);
        else if(index == ActionEmulate && prepare(app)) {
            lfrfid_worker_start_thread(app->worker);
            lfrfid_worker_emulate_start(app->worker, (LFRFIDProtocol)app->protocol);
            app->emulating = true;
            app->blink_on = true;
            app->blink_ticks = 0;
            notification_message_block(app->notifications, &rfid_led_on);
            furi_string_printf(app->display, "Emulating (v0.8)\n\n%s\n\nBack: stop emulation",
                               protocol_dict_get_name(app->dict, app->protocol));
            show_text(app, PageEmulate);
        }
    }
}
static void show_types(Maker *app) {
    app->page = PageTypes;
    submenu_reset(app->menu);
    submenu_set_header(app->menu, "RFID Maker v0.8");
    submenu_add_item(app->menu, "Open existing .rfid", ActionOpen, menu_callback, app);
    for(size_t i = 0; i < card_format_count; ++i) {
        ProtocolId id = protocol_dict_get_protocol_by_name(app->dict, card_formats[i].protocol);
        if(id != PROTOCOL_NO && protocol_dict_get_data_size(app->dict, id) == card_formats[i].size)
            submenu_add_item(app->menu, card_formats[i].label, i, menu_callback, app);
    }
    submenu_add_item(app->menu, "All types (advanced HEX)", ActionRaw, menu_callback, app);
    submenu_add_item(app->menu, "About", ActionAbout, menu_callback, app);
    view_dispatcher_switch_to_view(app->dispatcher, ViewMenu);
}
static void show_raw_types(Maker *app) {
    app->page = PageRawTypes;
    submenu_reset(app->menu);
    submenu_set_header(app->menu, "Advanced - raw protocol");
    for(size_t i = 0; i < LFRFIDProtocolMax; ++i)
        submenu_add_item(app->menu, protocol_dict_get_name(app->dict, i), i, menu_callback, app);
    view_dispatcher_switch_to_view(app->dispatcher, ViewMenu);
}
static void show_form(Maker *app) {
    app->page = PageForm;
    submenu_reset(app->menu);
    submenu_set_header(app->menu, app->format ? app->format->label
                                              : protocol_dict_get_name(app->dict, app->protocol));
    if(app->format) {
        for(size_t i = 0; i < app->format->count; ++i) {
            char label[64];
            snprintf(label, sizeof(label), "%s: %llu", app->format->fields[i].label,
                     app->values[i]);
            submenu_add_item(app->menu, label, i, menu_callback, app);
        }
    } else
        submenu_add_item(app->menu, "Edit HEX data", ActionEditRaw, menu_callback, app);
    submenu_add_item(app->menu, "Show HEX / details", ActionPreview, menu_callback, app);
    submenu_add_item(app->menu,
                     furi_string_empty(app->source_path) ? "Save .rfid" : "Save as .rfid",
                     ActionSave, menu_callback, app);
    submenu_add_item(app->menu, "Emulate", ActionEmulate, menu_callback, app);
    view_dispatcher_switch_to_view(app->dispatcher, ViewMenu);
}
static bool back_callback(void *context) {
    Maker *app = context;
    stop_emulating(app);
    switch(app->page) {
    case PageTypes:
        view_dispatcher_stop(app->dispatcher);
        break;
    case PageForm:
        if(app->format)
            show_types(app);
        else
            show_raw_types(app);
        break;
    case PageRawTypes:
    case PageLoadError:
    case PageAbout:
        show_types(app);
        break;
    default:
        show_form(app);
        break;
    }
    return true;
}
static bool custom_callback(void *context, uint32_t event) {
    Maker *app = context;
    if(event == EventOpen) {
        open_card(app);
        return true;
    }
    if(event == EventInput) {
        if(app->page == PageField) {
            const CardField *field = &app->format->fields[app->field];
            card_parse_decimal(app->buffer, field->min, field->max, &app->values[app->field]);
            show_form(app);
        } else if(app->page == PageName)
            save_card(app);
        return true;
    }
    if(event == EventBytes || event == EventNumber) {
        show_form(app);
        return true;
    }
    return false;
}
static void tick_callback(void *context) {
    Maker *app = context;
    if(!app->emulating)
        return;
    // Match the standard emulation pulse: 10 ms on in a 100 ms period.
    ++app->blink_ticks;
    if(app->blink_ticks == 1) {
        app->blink_on = false;
        notification_message(app->notifications, &rfid_led_off);
    } else if(app->blink_ticks == 10) {
        app->blink_ticks = 0;
        app->blink_on = true;
        notification_message(app->notifications, &rfid_led_on);
    }
}
int32_t rfid_maker_app(void *p) {
    UNUSED(p);
    Maker *app = malloc(sizeof(Maker));
    memset(app, 0, sizeof(Maker));
    app->gui = furi_record_open(RECORD_GUI);
    app->storage = furi_record_open(RECORD_STORAGE);
    app->dialogs = furi_record_open(RECORD_DIALOGS);
    app->notifications = furi_record_open(RECORD_NOTIFICATION);
    app->dict = protocol_dict_alloc(lfrfid_protocols, LFRFIDProtocolMax);
    app->worker = lfrfid_worker_alloc(app->dict);
    app->capacity = protocol_dict_get_max_data_size(app->dict);
    app->data = malloc(app->capacity);
    app->display = furi_string_alloc();
    app->source_path = furi_string_alloc();
    app->browse_path = furi_string_alloc_set(STORAGE_EXT_PATH_PREFIX "/lfrfid");
    app->menu = submenu_alloc();
    app->input = text_input_alloc();
    app->text = text_box_alloc();
    app->bytes = byte_input_alloc();
    app->number = number_input_alloc();
    app->dispatcher = view_dispatcher_alloc();
    view_dispatcher_set_event_callback_context(app->dispatcher, app);
    view_dispatcher_set_navigation_event_callback(app->dispatcher, back_callback);
    view_dispatcher_set_custom_event_callback(app->dispatcher, custom_callback);
    view_dispatcher_set_tick_event_callback(app->dispatcher, tick_callback, furi_ms_to_ticks(10));
    view_dispatcher_add_view(app->dispatcher, ViewMenu, submenu_get_view(app->menu));
    view_dispatcher_add_view(app->dispatcher, ViewInput, text_input_get_view(app->input));
    view_dispatcher_add_view(app->dispatcher, ViewText, text_box_get_view(app->text));
    view_dispatcher_add_view(app->dispatcher, ViewBytes, byte_input_get_view(app->bytes));
    view_dispatcher_add_view(app->dispatcher, ViewNumber, number_input_get_view(app->number));
    view_dispatcher_attach_to_gui(app->dispatcher, app->gui, ViewDispatcherTypeFullscreen);
    show_types(app);
    view_dispatcher_run(app->dispatcher);
    stop_emulating(app);
    for(unsigned i = 0; i < 5; ++i)
        view_dispatcher_remove_view(app->dispatcher, i);
    view_dispatcher_free(app->dispatcher);
    submenu_free(app->menu);
    text_input_free(app->input);
    text_box_free(app->text);
    byte_input_free(app->bytes);
    number_input_free(app->number);
    furi_string_free(app->display);
    furi_string_free(app->source_path);
    furi_string_free(app->browse_path);
    free(app->data);
    lfrfid_worker_free(app->worker);
    protocol_dict_free(app->dict);
    furi_record_close(RECORD_STORAGE);
    furi_record_close(RECORD_DIALOGS);
    furi_record_close(RECORD_NOTIFICATION);
    furi_record_close(RECORD_GUI);
    free(app);
    return 0;
}
