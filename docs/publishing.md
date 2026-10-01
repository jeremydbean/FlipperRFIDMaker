# Apps Catalog submission preparation

RFID Maker v0.8 has not been submitted to the catalog. This checklist records what is ready and what remains.

## Ready

- Public GitHub source and GPL-3.0-or-later license.
- `application.fam` with the RFID category, version, unique app identifier to be checked at submission, and KindaCharming author credit.
- Embedded 10x10 monochrome PNG icon.
- Successful uFBT build and SDK import check against official release 1.4.3 and Momentum mntm-012, both F7 / API 87.1.
- ARM import and emulation controller checks against both SDK header sets.
- `docs/catalog-description.md` for the catalog's supported Markdown subset.
- `docs/changelog.md`.
- Original qFlipper device-screen exports at `screenshots/ss0.png` and `screenshots/ss1.png`, copied byte-for-byte without resizing (v0.7).

## Still required

- Check v0.8 on a physical Flipper running the supported official firmware: opening, editing, HEX preview, saving, emulation, Back, About, and exit.
- Optionally refresh the screenshots to v0.8 and add About/HEX previews using qFlipper **Save Screenshot**, retaining the original dimensions and format. Existing exports show v0.7.
- Pin the submission manifest to the source commit containing those exports and the final tested app.
- Check that `rfid_maker` is available in the catalog and run its bundle validator.

## Catalog manifest

Place the final manifest in the catalog repository at `applications/RFID/rfid_maker/manifest.yml`:

```yaml
sourcecode:
  type: git
  location:
    origin: https://github.com/jeremydbean/FlipperRFIDMaker.git
    commit_sha: REPLACE_WITH_FINAL_SOURCE_COMMIT
description: "@docs/catalog-description.md"
changelog: "@docs/changelog.md"
screenshots:
  - screenshots/ss0.png
  - screenshots/ss1.png
```

The remaining app metadata is read from `application.fam`. The separate catalog description keeps build instructions and repository documentation out of the catalog listing.

## Validate and submit

In a checkout of the official catalog, install `tools/requirements.txt` in a virtual environment and configure uFBT for official release firmware. Run:

```sh
python tools/bundle.py --nolint applications/RFID/rfid_maker/manifest.yml bundle.zip
```

Fix validation errors before submitting a pull request. Fill in the catalog's PR template and describe the physical-device checks actually completed. Do not mark unchecked items as passed. Catalog maintainers review the submission; this repository preparation does not publish the app.

## References

- [Official contribution guide](https://github.com/flipperdevices/flipper-application-catalog/blob/main/documentation/Contributing.md)
- [Manifest specification and validation](https://github.com/flipperdevices/flipper-application-catalog/blob/main/documentation/Manifest.md)
