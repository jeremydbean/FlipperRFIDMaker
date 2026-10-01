// SPDX-License-Identifier: GPL-3.0-or-later
#include "decimal_input.h"
#include "card_formats.h"
#include <furi.h>
#include <stdio.h>
#include <string.h>

struct DecimalInput {
    View *view;
};
typedef struct {
    char header[64];
    char text[21]; // Full uint64 decimal range plus terminator.
    uint64_t min, max;
    bool replace;
    uint8_t row, column;
    DecimalInputCallback callback;
    void *context;
} DecimalModel;

static bool decimal_valid(DecimalModel *model, uint64_t *value) {
    return card_parse_decimal(model->text, model->min, model->max, value);
}

static void decimal_draw(Canvas *canvas, void *context) {
    DecimalModel *model = context;
    canvas_set_font(canvas, FontSecondary);
    canvas_draw_str(canvas, 2, 9, model->header);
    canvas_draw_frame(canvas, 2, 12, 124, 16);
    canvas_draw_str(canvas, 5, 23, model->text);
    char range[48];
    snprintf(range, sizeof(range), "%llu-%llu", model->min, model->max);
    canvas_draw_str(canvas, 2, 36, range);
    uint64_t value;
    bool valid = decimal_valid(model, &value);
    for(unsigned row = 0; row < 2; ++row) {
        for(unsigned column = 0; column < 6; ++column) {
            unsigned x = column < 5 ? 3 + column * 15 : 83;
            unsigned y = 38 + row * 13;
            bool selected = model->row == row && model->column == column;
            if(selected) {
                canvas_draw_box(canvas, x, y, column < 5 ? 13 : 42, 12);
                canvas_set_color(canvas, ColorWhite);
            }
            char digit[2] = {(char)('0' + row * 5 + column), 0};
            canvas_draw_str(canvas, x + 2, y + 10,
                            column < 5 ? digit
                            : row == 0 ? "Del"
                            : valid    ? "Save"
                                       : "Invalid");
            canvas_set_color(canvas, ColorBlack);
        }
    }
}

static bool decimal_event(InputEvent *event, void *context) {
    DecimalInput *input = context;
    if(event->key == InputKeyBack ||
       (event->type != InputTypeShort && event->type != InputTypeRepeat))
        return false;
    DecimalModel *model = view_get_model(input->view);
    DecimalInputCallback callback = NULL;
    void *callback_context = NULL;
    uint64_t value = 0;
    switch(event->key) {
    case InputKeyUp:
        model->row = 0;
        break;
    case InputKeyDown:
        model->row = 1;
        break;
    case InputKeyLeft:
        model->column = (model->column + 5) % 6;
        break;
    case InputKeyRight:
        model->column = (model->column + 1) % 6;
        break;
    case InputKeyOk:
        // Holding OK must not enter a stream of unintended digits or save twice.
        if(event->type != InputTypeShort)
            break;
        if(model->column == 5) {
            if(model->row == 0) {
                size_t length = strlen(model->text);
                if(length)
                    model->text[length - 1] = 0;
                model->replace = false;
            } else if(decimal_valid(model, &value)) {
                callback = model->callback;
                callback_context = model->context;
            }
        } else {
            // Existing values remain visible; the first digit replaces them.
            // Explicit Del switches to editing the existing value instead.
            char candidate[21];
            size_t length = model->replace ? 0 : strlen(model->text);
            if(length < sizeof(candidate) - 1) {
                memcpy(candidate, model->text, length);
                candidate[length] = '0' + model->row * 5 + model->column;
                candidate[length + 1] = 0;
                uint64_t parsed;
                // Permit prefixes below min; enforce min only when saving.
                if(card_parse_decimal(candidate, 0, model->max, &parsed)) {
                    memcpy(model->text, candidate, length + 2);
                    model->replace = false;
                }
            }
        }
        break;
    default:
        break;
    }
    // Release the model lock before a callback changes application state.
    view_commit_model(input->view, true);
    if(callback)
        callback(callback_context, value);
    return true;
}

DecimalInput *decimal_input_alloc(void) {
    DecimalInput *input = malloc(sizeof(DecimalInput));
    input->view = view_alloc();
    view_allocate_model(input->view, ViewModelTypeLocking, sizeof(DecimalModel));
    view_set_context(input->view, input);
    view_set_draw_callback(input->view, decimal_draw);
    view_set_input_callback(input->view, decimal_event);
    return input;
}
void decimal_input_free(DecimalInput *input) {
    view_free(input->view);
    free(input);
}
View *decimal_input_get_view(DecimalInput *input) { return input->view; }
void decimal_input_configure(DecimalInput *input, const char *header, uint64_t value, uint64_t min,
                             uint64_t max, bool blank, DecimalInputCallback callback,
                             void *context) {
    DecimalModel *model = view_get_model(input->view);
    memset(model, 0, sizeof(*model));
    snprintf(model->header, sizeof(model->header), "%s", header);
    if(!blank)
        snprintf(model->text, sizeof(model->text), "%llu", value);
    model->min = min;
    model->max = max;
    model->replace = !blank;
    model->callback = callback;
    model->context = context;
    view_commit_model(input->view, true);
}
