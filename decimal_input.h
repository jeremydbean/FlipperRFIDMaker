// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <gui/view.h>
#include <stdint.h>

typedef struct DecimalInput DecimalInput;
typedef void (*DecimalInputCallback)(void *context, uint64_t value);
DecimalInput *decimal_input_alloc(void);
void decimal_input_free(DecimalInput *input);
View *decimal_input_get_view(DecimalInput *input);
void decimal_input_configure(DecimalInput *input, const char *header, uint64_t value, uint64_t min,
                             uint64_t max, bool blank, DecimalInputCallback callback,
                             void *context);
