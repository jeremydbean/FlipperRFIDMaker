# Apps Catalog submission status

RFID Maker is submitted for review in [catalog PR #1274](https://github.com/flipperdevices/flipper-application-catalog/pull/1274). v0.9 adds the numeric-entry fixes. Physical-device testing on official firmware remains pending and is disclosed in the submission.

## Ready

- Public GitHub source and GPL-3.0-or-later license.
- `application.fam` with the RFID category, version 0.9, app identifier rfid_maker, and KindaCharming author credit.
- Embedded 10x10 monochrome PNG icon.
- Successful uFBT build and SDK import check against official release 1.4.3 and Momentum mntm-012, both F7 / API 87.1.
- ARM import and emulation controller checks against both SDK header sets.
- ARM numeric keypad tests for all 42 fields across 18 presets: blank new entries, full minimum/maximum bounds, replacement, deletion, zero, overflow rejection, cancellation and repeated OK.
- Catalog bundle validation passed for the pinned v0.9 source, including an official-firmware source build.
- `docs/catalog-description.md` for the catalog's supported Markdown subset.
- `docs/changelog.md`.
- Original qFlipper device-screen exports at `screenshots/ss0.png` and `screenshots/ss1.png`, copied byte-for-byte without resizing (v0.7).

## Still required

- Check v0.9 on a physical Flipper running the supported official firmware: opening, editing, blank numeric entries, full field limits, HEX preview, saving, emulation, Back, About, and exit.
- Optionally refresh the screenshots to v0.9 and add About/HEX previews using qFlipper **Save Screenshot**, retaining the original dimensions and format. Existing exports show v0.7.
- Address any maintainer feedback in the existing pull request and rerun validation after source or manifest changes.
- Obtain catalog maintainer review and approval. Submission alone does not publish the app.

## Catalog manifest

The submitted manifest is at `applications/RFID/rfid_maker/manifest.yml` in the catalog pull request. It pins the tested app and original screenshots to this source revision:

```yaml
sourcecode:
  type: git
  location:
    origin: https://github.com/jeremydbean/FlipperRFIDMaker.git
    commit_sha: 39ff1e359257197140ba6b1fa2ac530fc39f9296
description: "@docs/catalog-description.md"
changelog: "@docs/changelog.md"
screenshots:
  - screenshots/ss0.png
  - screenshots/ss1.png
```

The remaining app metadata is read from `application.fam`. The separate catalog description keeps build instructions and repository documentation out of the catalog listing. Later documentation commits on main do not automatically change the pinned catalog submission.

## Validate future submission updates

In a checkout of the official catalog, install `tools/requirements.txt` in a virtual environment and configure uFBT for official release firmware. Run:

```sh
python tools/bundle.py --nolint applications/RFID/rfid_maker/manifest.yml bundle.zip
```

Fix validation errors before updating the existing pull request. Update its manifest pin when submitting a new source revision, and describe the physical-device checks actually completed. Do not mark unchecked items as passed. The submission discloses AI-generated implementation and pending physical-device tests; leave the reviewer checklist for maintainers.

## References

- [Official contribution guide](https://github.com/flipperdevices/flipper-application-catalog/blob/main/documentation/Contributing.md)
- [Manifest specification and validation](https://github.com/flipperdevices/flipper-application-catalog/blob/main/documentation/Manifest.md)
