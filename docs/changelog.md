# Changelog

## v0.8

- Added Proxmark ID/raw HEX for seven presets and H10301 sheet-style HEX.
- Checked HID raw values against actual Proxmark3 C packers in 2,004 vectors.
- Added About to the type menu with Created by: KindaCharming.
- Updated the app author metadata to KindaCharming.
- Built and checked SDK imports against official firmware 1.4.3, F7 / API 87.1, as well as Momentum mntm-012.
- Added catalog description, publishing checklist, and README screenshots.

## v0.7

- Changed the emulation indicator to a rapid 10 ms pulse every 100 ms.

## v0.6

- Controlled all RGB notification channels during emulation so USB charging green does not mask the pulse.
- Alternated magenta/off and restored normal status lighting on stop.
- Displayed the version on the type menu and emulation screen.

## v0.5

- Added notification service lifecycle and an emulation blink request.

## v0.4

- Fixed opening RFID files stopping the app's view dispatcher.
- Deferred the file browser until the menu input callback returned.
- Added ARM controller regression tests for import and recovery.

## v0.3

- Provided 18 decimal presets, HEX preview, saving and emulation.
- Added the embedded RFID app icon.
- Added import, lossless decimal recognition, HEX fallback and Save as.
