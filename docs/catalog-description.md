# RFID Maker

Created by: **KindaCharming**

Create and edit 125 kHz RFID files using decimal facility codes and card numbers. Select a format, enter its decimal fields, inspect the generated HEX data, then save or emulate the card.

## Features

- 18 decimal presets with field limits and additional fields where required.
- Blank new card-number entries and a numeric keypad showing each field's valid range. Typing replaces an existing value; Del edits it.
- Open existing .rfid files and automatically fill supported decimal forms.
- Preserve unsupported layouts in the advanced HEX editor.
- Save edited copies without overwriting the original file.
- Preview the stored data, the firmware interpretation, and verified Proxmark ID/raw HEX for HID H10301/H10306, EM4100, Indala26 and AWID. H10301 also shows sheet-style HEX without the format marker. Other layouts report that Proxmark conversion is not implemented.
- Emulate directly, with a rapid magenta LED pulse and Back to stop.
- About screen with creator credit.

## Supported decimal formats

HID H10301, HID H10306, EM4100 RF/64, RF/32 and RF/16, Indala26, IO Prox XSF, AWID26, Pyramid26, Gallagher, Keri, Securakey26, Viking, PAC/Stanley, Jablotron, IDTECK, Paradox and GProx II26.

A protocol can contain several layouts. Decimal conversion supports these presets; other layouts use HEX editing. Some formats require extra information such as a prefix, region, issue level or check bytes. This app does not handle 13.56 MHz NFC cards.

## Use

- Select a type and enter its decimal fields.
- Select **Show HEX / details** to inspect the result.
- Select **Save .rfid** to save under SD/lfrfid, or **Emulate** to start emulation.
- Select **Open existing .rfid** to edit a saved file. **Save as .rfid** creates a new copy.
- Select **About** at the bottom of the type menu for version and creator information.

## License

GPL-3.0-or-later.
