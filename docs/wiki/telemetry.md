---
layout: wiki
title: Telemetry and Privacy
permalink: /wiki/telemetry/
---

TI-Toolbox can send opt-in usage telemetry to help maintainers understand feature adoption and
failures. This page lists the current payload and controls; [Troubleshooting]({{ site.baseurl }}/wiki/troubleshooting/)
explains what to include when you deliberately send a diagnostic report.

## Consent and controls

Telemetry is **off by default**. Events are sent only when the user-level `enabled` preference is
true; the adjacent `consent_shown` value records whether the choice has been presented. The
supported controls update both values together.

- In the application, use **Settings → Project → Telemetry → Send anonymous usage data**. The change takes
  effect immediately and applies to every project opened by that user.
- From the scientific Python environment, consent can be recorded explicitly with
  `from tit.telemetry import set_enabled; set_enabled(True)`. The `consent_prompt_cli()` helper
  asks once only when a caller invokes it in an interactive terminal; non-interactive input does
  not opt in. Use `set_enabled(False)` to withdraw consent.
- Set `TIT_NO_TELEMETRY=1` (also `true` or `yes`, case-insensitive) to suppress sending
  immediately, regardless of the saved preference.

The preference and a random per-install client UUID live in `telemetry.json`:

| Environment | Location |
|---|---|
| macOS | `~/.config/ti-toolbox/telemetry.json` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/ti-toolbox/telemetry.json` |
| Windows | `%APPDATA%\ti-toolbox\telemetry.json` |
| Running container | `/root/.config/ti-toolbox/telemetry.json`, mounted from the host |

The file is written with owner read/write permissions (`0600`). It persists across projects and
container restarts. Deleting it creates a new random client UUID and returns telemetry to its
disabled, not-yet-answered state.

## Data sent

Every event contains:

| Field | Meaning |
|---|---|
| `client_id` | Random 32-character UUID generated for this installation; it is not derived from an account or device identifier |
| event name | Operation category such as `sim_ti`, `flex_search`, `analysis`, `pre_fastsurfer`, `stats_comparison`, `report_generate`, or a Blender export |
| `tit_version` | Installed TI-Toolbox version |
| `os_name` | Host OS normalized to `darwin`, `linux`, `windows`, or `unknown` |
| `os_version` | Host OS release |
| `platform` | Host CPU architecture normalized to values such as `x86_64` or `arm64` |
| `interface` | Calling interface, normally `gui` or `cli` |

Tracked operations send a `start` event and then a `success` or `error` event. Their event-specific
fields are:

| Field | When present | Meaning |
|---|---|---|
| `status` | Every operation event | `start`, `success`, or `error` |
| `run_id` | Every operation event | Random UUID joining one start event to its completion event |
| `duration_s` | Success or error | Rounded wall-clock duration in seconds |
| `error_type` | Error | Exception class name |
| `error_detail` | Error | Exception message trimmed to 80 characters after slash-prefixed path text is replaced with `<path>` |
| `error_fingerprint` | Error | First 16 hexadecimal characters of a hash over the exception type, final traceback location (file basename, function, line), and sanitized detail |

The first opt-in also sends one `first_open` event. Current operation categories cover TI/mTI
simulation; flex and exhaustive optimization; individual and group analysis; preprocessing and
its CHARM, FastSurfer, DICOM, QSIPrep and QSIRecon stages; statistics; report generation; and
montage, region and vector exports.

The payload contains no dedicated field for a project path or name, subject identifier, directory
tree, scientific result, montage, electrode position, ROI, stimulation parameter, hostname,
username, Python version, or full traceback. Error events do include the short detail described
above; it is not the full message or traceback, but free-form exception text can contain context,
and the sanitizer specifically replaces slash-prefixed path text.

Events are posted to Google Analytics 4. No IP-address field is included in the JSON payload;
Google necessarily receives the network connection and may derive approximate geographic
location under its GA4 processing. See Google's
[Measurement Protocol documentation](https://developers.google.com/analytics/devguides/collection/protocol/ga4)
for that service's processing terms.

## Delivery behavior

Ordinary sends run in a background daemon thread with a five-second network timeout. Completion
and error events wait briefly for that sender so they are less likely to disappear when a worker
exits. Network, DNS, TLS, or service failures are dropped and never turn a scientific operation
into a failure.

The implementation and tests are the final authority for the payload:
[`tit/telemetry.py`](https://github.com/idossha/TI-toolbox/blob/main/tit/telemetry.py) and
[`tests/test_telemetry.py`](https://github.com/idossha/TI-toolbox/blob/main/tests/test_telemetry.py).
