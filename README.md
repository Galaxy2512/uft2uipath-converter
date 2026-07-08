# uft2uipath converter v0.2

General ALM/UFT BPT `.qcp` → UiPath Test Project converter foundation.

## What v0.2 does

- extracts `.qcp` using Python ZIP and falls back to 7-Zip when ALM ZIP headers are non-standard
- scans ALM/QC project export files safely
- discovers BPT-like business components generically, not only one fixed sample
- classifies common UFT/BPT operations into an intermediate model
- generates a valid UiPath Test Project (`project.json`, `Main.xaml`, `TestCases`, components)
- writes `Data/migration_model.json`
- writes `Reports/ConversionReport.md` with warnings and unsupported/TODO items

## What v0.2 intentionally does not fake

- selectors / Object Repository entries
- custom VBScript functions
- complex BPT flow reconstruction when ALM table relationships are not decoded yet
- native UIAutomation activities for selector-dependent operations

Unknown or risky mappings are kept as explicit TODO steps so the converter does not silently generate wrong tests.

## Run

```powershell
cd C:\Users\KristinaŠeparović\Documents\uft2uipath_converter_v02
py -m uft2uipath.cli "..\Migration_BPT.qcp" --out "..\Generated_By_Converter_v03" --zip
```

Then open:

```text
C:\Users\KristinaŠeparović\Documents\Generated_By_Converter_v03\project.json
```

Review:

```text
Reports\ConversionReport.md
Data\migration_model.json
```

## Roadmap

- v0.3: decode ALM BPT table relationships more deeply and reconstruct component order without hints
- v0.4: Object Repository/selector extraction and mapping
- v0.5: generate native UiPath activity templates for browser, navigate, click, type, select, verify, Excel
- v1.0: Test Manager import/export integration and broader UFT operation coverage
