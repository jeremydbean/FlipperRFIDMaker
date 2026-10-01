// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CARD_MAX_FIELDS 5
typedef struct {
    const char *label;
    uint64_t min;
    uint64_t max;
    uint64_t initial;
} CardField;
typedef enum {
    CardHid26,
    CardEm,
    CardIndala,
    CardIo,
    CardAwid,
    CardPyramid,
    CardGallagher,
    CardKeri,
    CardSecurakey,
    CardId,
    CardIdteck,
    CardParadox,
    CardGprox,
    CardHid34,
} CardEncoding;
typedef struct {
    const char *label;
    const char *protocol;
    const char *note;
    CardEncoding encoding;
    size_t size;
    size_t count;
    CardField fields[CARD_MAX_FIELDS];
} CardFormat;
extern const CardFormat card_formats[];
extern const size_t card_format_count;
bool card_parse_decimal(const char *text, uint64_t min, uint64_t max, uint64_t *value);
bool card_encode(const CardFormat *format, const uint64_t *values, uint8_t *data, size_t size);
// Accept a decimal form only when re-encoding preserves every stored data byte.
bool card_decode(const CardFormat *format, const uint8_t *data, size_t size, uint64_t *values);
// Return bytes in Proxmark's ID/raw representation, or zero for unsupported layouts.
size_t card_proxmark_raw(const CardFormat *format, const uint8_t *data, size_t size, uint8_t *raw,
                         size_t capacity);
