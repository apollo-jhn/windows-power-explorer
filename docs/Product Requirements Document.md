# Product Requirements Document (PRD)

* **Document Version:** 4.0.0 (Python + customtkinter + ctypes Stack)
* **Target OS:** Windows 10 (19041+) & Windows 11 (x64; ARM64 via emulation)
* **Tech Stack:** Python 3.10+, `ctypes` (`PowrProf.dll`), `customtkinter` 6.0.0
* **Related Documents:** [[Index]], [[Technical Design Document]], [[Win32 API Reference]], [[Architecture Decision Records]], [[Design Specification]], [[Recovery and Destructive Operations]]

---

## 1. Executive Summary

Existing utilities like *PowerSettingsExplorer* expose raw 128-bit GUIDs in an outdated WinForms grid, lack search/filtering, and do not support creating custom power schemes.

**Windows Power Explorer** is a clean, modern, lightweight desktop application written in **Python**, using **`customtkinter`** for a dark-themed UI and **`ctypes`** for Win32 `PowrProf.dll` interop.

It allows users to:
1. Access and edit **all hidden Windows power settings per profile**.
2. **Unhide settings** in the native Windows Control Panel (`powercfg.cpl`).
3. **Create new custom power schemes** derived from default Windows base profiles.

---

## 2. Personas

| Persona | Need | What they use |
| :--- | :--- | :--- |
| **Enthusiast / overclocker** | Tune CPU boost, PCIe ASPM, and processor states beyond what Control Panel exposes | GUI, deep settings, per-scheme AC/DC editing |
| **Laptop owner chasing battery life** | Understand and change what actually drains the battery on DC | GUI, search, DC column, hazard warnings |
| **IT technician / sysadmin** | Apply a known-good power configuration across many machines | CLI, JSON presets, `unhide-all` |
| **Curious user** | See what all those hidden settings are without breaking anything | GUI, search, descriptions, restore-defaults safety net |

---

## 3. Product Scope & Non-Goals

### 3.1 In-Scope (Core Pillars)
1. **Base Scheme Builder & CRUD:** Create custom power schemes by cloning existing schemes. Edit, rename, duplicate, delete, and switch active profiles.
2. **Access All Hidden Settings:** Enumerate every power setting across all subgroups (CPU, GPU, Display, Sleep, PCIe, Storage, Peripherals).
3. **Per-Profile AC/DC Value Editor:** Edit Plugged-in (AC) and On Battery (DC) values per scheme with sliders, dropdowns, and toggles.
4. **Control Panel Visibility Manager:** Show or hide settings in the native Windows Power Options GUI (`powercfg.cpl`), system-wide.
5. **JSON Preset Export & Import:** Export schemes to portable JSON; import JSON presets and `.pow` files.
6. **Search & Category Filtering:** Instant search and category sidebar to locate settings without touching raw GUIDs.
7. **Recovery:** Restore Windows default power schemes and restore default Control Panel visibility, both with backups.

### 3.2 Explicit Out-of-Scope
* ❌ **No Telemetry / Hardware Monitoring:** No CPU clock tracking, battery discharge graphs, or system monitoring counters.
* ❌ **No Process Automation:** No background service, process watchers, or WMI application triggers.
* ❌ **No Kernel Overclocking:** Operates strictly within standard Windows Win32 Power Management APIs.
* ❌ **No `.pow` export.** No such API exists (ADR-007). `.pow` *import* is supported.
* ❌ **No writing Windows 11 Power Mode overlays.** Read and display only (ADR-009).
* ❌ **No network access of any kind.** No updates, no telemetry, no crash reporting.
* ❌ **No screen-reader support.** A permanent consequence of ADR-002, disclosed to users.

---

## 4. Technical Stack & Architecture

### 4.1 Technology Stack
* **Language:** Python 3.10+
* **GUI Framework:** [`customtkinter`](https://github.com/TomSchimansky/CustomTkinter) 6.0.0
* **Win32 Interop:** `ctypes` (C-FFI to `PowrProf.dll`, `kernel32.dll`, `shell32.dll`) plus `winreg` for visibility attributes
* **CLI:** `argparse`
* **Packaging:** `PyInstaller` — onefile and onedir artifacts (ADR-010)

### 4.2 Project Module Structure

This is the **canonical** module tree. [[Technical Design Document]] and [[Design Specification]] follow it.

```text
windows_power_explorer/
├── main.py                          # Entry point: GUI launch, CLI dispatch, elevated-helper mode
├── core/
│   ├── __version__.py               # Single source of truth for the version string
│   ├── win32_bindings.py            # ctypes prototypes — see [[Win32 API Reference]]
│   ├── power_manager.py             # High-level API for scheme CRUD & setting read/write
│   ├── catalog.py                   # Phase-1 scheme-invariant setting catalog (ADR-012)
│   ├── values.py                    # Phase-2 per-scheme values & personality defaults
│   ├── compare.py                   # Scheme diff & modified-from-default computation
│   ├── visibility.py                # winreg Attributes read/write (ADR-006)
│   ├── overlay.py                   # Windows 11 power mode overlay, read-only (ADR-009)
│   ├── models.py                    # Dataclasses: catalog entries, values, schemes
│   ├── controller.py                # AppController: worker threads, result queue, state
│   ├── presets.py                   # JSON preset export / import / validation
│   ├── script_export.py             # powercfg script & Markdown generators (ADR-013)
│   ├── elevation.py                 # Elevated helper launch & batch protocol (ADR-008)
│   ├── errors.py                    # Exception hierarchy & Win32 message map
│   ├── paths.py                     # Portable vs LOCALAPPDATA root resolution (ADR-014)
│   ├── instance.py                  # Single-instance mutex & window activation
│   └── ui_state.py                  # Geometry, favorites, theme, last selection (ADR-005)
├── cli/
│   ├── parser.py                    # argparse definitions
│   └── commands.py                  # Subcommand implementations & exit codes
├── ui/
│   ├── app.py                       # customtkinter.CTk main window shell & layout
│   ├── sidebar.py                   # CTkScrollableFrame category & profile navigator
│   ├── search_bar.py                # CTkEntry search & filter header
│   ├── status_bar.py                # Footer: status text, active scheme, overlay indicator
│   ├── theme.py                     # Light/dark/system palette resolution
│   ├── components/
│   │   ├── setting_card.py          # Setting card with AC/DC controls & default badge
│   │   ├── visibility_row.py        # Row widget for the Control Panel Visibility view
│   │   └── diff_row.py              # Row widget for the scheme comparison view
│   ├── views/
│   │   ├── visibility_view.py       # Global visibility manager (ADR-006)
│   │   └── compare_view.py          # Side-by-side scheme comparison
│   └── dialogs/
│       ├── base.py                  # ConfirmDialog, typed-phrase confirmation (ADR-011)
│       ├── create_scheme_dialog.py  # CTkToplevel modal for cloning schemes
│       ├── command_palette.py       # Ctrl+K fuzzy jump
│       ├── export_dialog.py         # Format selection: JSON / powercfg / Markdown
│       └── elevation_dialog.py      # Explains why Administrator is needed
├── data/
│   ├── essentials.json              # Curated starter setting list (UI hint, not power data)
│   ├── reboot_required.json         # Settings needing reboot/replug to take effect
│   └── doc_links.json               # Microsoft Learn URLs for known settings
├── schema/
│   └── power_preset.schema.json     # Formal preset contract (test-time validation)
└── assets/                          # App icons & themes
```

> [!NOTE]
> Files under `data/` are **UI metadata, not power data.** They describe how to present
> settings, never what a setting's value is. ADR-005 is unaffected — the registry remains
> the sole source of truth for every value the app reads or writes. Each file is optional:
> a missing or malformed entry degrades that one presentational feature and nothing else.

---

## 5. Win32 Integration Summary

Full signatures, buffer protocols, and memory ownership are in **[[Win32 API Reference]]**, which is authoritative. Summary:

| Task | Mechanism | Privilege |
| :--- | :--- | :--- |
| **Enumerate schemes / subgroups / settings** | `PowerEnumerate` | Standard User |
| **Clone scheme** | `PowerDuplicateScheme` | Standard User |
| **Set active scheme** | `PowerSetActiveScheme` | Standard User |
| **Read AC/DC values** | `PowerReadACValueIndex`, `PowerReadDCValueIndex` | Standard User |
| **Write AC/DC values** | `PowerWriteACValueIndex`, `PowerWriteDCValueIndex` | Standard User |
| **Read value bounds** | `PowerReadValueMin` / `Max` / `Increment` / `UnitsSpecifier` | Standard User |
| **Read enum choices** | `PowerReadPossibleValue`, `PowerReadPossibleFriendlyName` | Standard User |
| **Rename / describe** | `PowerWriteFriendlyName`, `PowerWriteDescription` | Standard User |
| **Delete scheme** | `PowerDeleteScheme` | Standard User |
| **Import scheme** | `PowerImportPowerScheme` (`.pow`) or `core/presets.py` (JSON) | Standard User |
| **Export scheme** | `core/presets.py` → JSON. **No Win32 export API exists.** | Standard User |
| **Read visibility** | `PowerReadSettingAttributes` | Standard User |
| **Write visibility** | **`winreg` direct write** — `Attributes = 2` to show, `1` to hide (ADR-006) | **Administrator** |
| **Check policy lock** | `PowerSettingAccessCheck` | Standard User |
| **Read power mode overlay** | `PowerGetEffectiveOverlayScheme` *(undocumented)* | Standard User |
| **Restore defaults** | `PowerRestoreDefaultPowerSchemes` | **Administrator** |

---

## 6. Functional Requirements

### Requirement 1: Scheme Duplication & Custom Scheme Creation

* **REQ-1.1:** The app SHALL provide a modal dialog (`CTkToplevel`) offering a dropdown (`CTkOptionMenu`) of schemes available to clone.

  The dropdown SHALL be populated from a **live `PowerEnumerate(ACCESS_SCHEME)` pass**, not from a hardcoded list. Known base schemes are matched against this table for display name and sort order; **entries not present on the machine are omitted, not offered**.

  | Base scheme | GUID |
  | :--- | :--- |
  | Balanced | `381b4222-f694-41f0-9685-ff5bb260df2e` |
  | High Performance | `8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c` |
  | Power Saver | `a1841308-3541-4fab-bc81-f71556f20b4a` |
  | Ultimate Performance | `e9a42b02-d5df-448d-aa00-03f14749eb61` |

  > **Why:** on Modern Standby machines Windows exposes only *Balanced*; the others are hidden or absent, and *Ultimate Performance* does not exist until duplicated. A hardcoded list produces clone buttons that fail with `ERROR_FILE_NOT_FOUND`.

* **REQ-1.2:** Clicking **"Create"** SHALL call `PowerDuplicateScheme` to generate a new GUID, then apply the user's name via `PowerWriteFriendlyName` and description via `PowerWriteDescription`.
* **REQ-1.3:** Custom schemes SHALL be visually distinguished from built-in schemes in the sidebar, and built-in schemes SHALL NOT offer a delete control.
* **REQ-1.4:** The **power plan personality** setting (`245d8541-3943-4422-b025-13a784f679b7`, in `NO_SUBGROUP_GUID`) SHALL be set to match the chosen base template on clone, and SHALL be surfaced as a prominent, plain-language card rather than buried among other settings.

  > **Why:** this value takes precedence over individual settings. A scheme cloned from Balanced with every processor value copied from High Performance still behaves like Balanced until the personality changes. Users hit this and conclude the app does not work.

### Requirement 2: Access & Edit All Settings Per Profile

* **REQ-2.1:** The app SHALL enumerate all power settings across all subgroups using `PowerEnumerate`, on a background worker thread (ADR-003).
* **REQ-2.2:** Setting cards SHALL allow editing AC (Plugged In) and DC (Battery) values independently for the scheme selected in the sidebar.
* **REQ-2.3:** Changes SHALL be written via `PowerWriteACValueIndex` / `PowerWriteDCValueIndex`.

  **`PowerSetActiveScheme` SHALL be called only when the edited scheme is the currently active scheme.** Edits to non-active schemes persist immediately and apply when that scheme is next activated.

  > **Why:** `PowerSetActiveScheme` *makes* a scheme active. Calling it to "refresh" after editing an inactive scheme silently switches the user's machine onto the plan they were merely inspecting.

* **REQ-2.4:** Control type SHALL be inferred from the setting's metadata: enum → `CTkOptionMenu`, 0/1 range → `CTkSwitch`, wider range → `CTkSlider`, unreadable bounds → read-only label.
* **REQ-2.5:** Settings blocked by a Group Policy override SHALL be detected during enumeration via `PowerSettingAccessCheck` and rendered **disabled with an explanatory tooltip**, never allowed to fail on write.
* **REQ-2.6:** Machines without a battery SHALL render the DC column as unavailable rather than showing misleading zeroes.
* **REQ-2.7:** Setting names SHALL come from `PowerReadFriendlyName` in the OS display language. Where Windows returns no name, the app SHALL display the GUID with an "Unknown setting" label and keep the setting editable. Search SHALL match both friendly name and GUID.

### Requirement 3: Control Panel Visibility Manager

* **REQ-3.1:** The app SHALL provide a dedicated **Control Panel Visibility** view listing every setting with a `CTkSwitch` controlling its visibility in `powercfg.cpl`.

  > **Why a separate view:** visibility is stored globally under `…\Control\Power\PowerSettings\`, independent of any scheme, and applies to all users. Placing the switch on a per-scheme setting card would tell users it is scoped to that scheme when it is not (ADR-006).

* **REQ-3.2:** The view SHALL carry a persistent banner stating that changes are system-wide, affect all users, and require Administrator.
* **REQ-3.3:** Toggling visibility SHALL write `Attributes` directly via `winreg`: `2` to show, `1` to hide. Revealing a setting SHALL also reveal its parent subgroup.
* **REQ-3.4:** Visibility state SHALL be read via `PowerReadSettingAttributes`, which correctly inherits subgroup attributes.
* **REQ-3.5:** Changes SHALL be batched. Toggles accumulate as pending edits and are committed by an **Apply** action that raises a single UAC prompt via the elevated helper (ADR-008).
* **REQ-3.6:** The app SHALL offer **Show All** and **Restore Control Panel Defaults**, the latter replaying the prior-state backup ([[Recovery and Destructive Operations]] §5).
* **REQ-3.7:** On launch the app SHALL detect visibility state differing from the last applied batch — which a Windows feature update causes — and offer to re-apply.

### Requirement 4: Preset Export & Import

* **REQ-4.1:** The app SHALL export any scheme to a JSON preset conforming to `schema/power_preset.schema.json`.
* **REQ-4.2:** The app SHALL import JSON presets and `.pow` files. `.pow` import uses `PowerImportPowerScheme`.
* **REQ-4.3:** Import SHALL create a new scheme by default and SHALL NOT silently overwrite an existing one.
* **REQ-4.4:** Import SHALL present a **diff preview** before writing anything, listing changed values, settings absent on this machine, and any visibility changes requiring elevation.
* **REQ-4.5:** Values outside this machine's live bounds SHALL be clamped with a warning rather than rejected, since hardware differs between exporting and importing machines.

### Requirement 5: Search, Filtering & Navigation

* **REQ-5.1:** The search bar SHALL filter settings live, matching friendly name, description, and GUID, case-insensitively.
* **REQ-5.2:** The sidebar SHALL offer category filters mapped to subgroups, plus "All".
* **REQ-5.3:** Search and category filters SHALL compose.
* **REQ-5.4:** An empty result SHALL show an explanatory empty state, not a blank pane.

### Requirement 6: Recovery & Safety

* **REQ-6.1:** The app SHALL offer **Restore Windows Default Power Schemes**, gated by the flow in [[Recovery and Destructive Operations]] §3, including a mandatory automatic backup of all custom schemes.
* **REQ-6.2:** Deleting a scheme SHALL require typed-name confirmation and SHALL warn when the target is the active scheme.
* **REQ-6.3:** Values with surprising consequences SHALL carry inline warnings. **They SHALL NOT be blocked** — every value Windows accepts is permitted.
* **REQ-6.4:** Values outside `PowerReadValueMin`/`Max` SHALL be rejected before the write with a clear message.

### Requirement 7: Power Mode Overlay Awareness

* **REQ-7.1:** The status bar SHALL display the active Windows 11 power mode overlay when available.
* **REQ-7.2:** When the overlay is not *Balanced*, the app SHALL explain that it modifies effective behaviour on top of the selected scheme.
* **REQ-7.3:** The app SHALL NOT write the overlay. Users are directed to Windows Settings (ADR-009).
* **REQ-7.4:** Absence of overlay support SHALL hide the indicator silently. It is never an error.

### Requirement 8: Scheme Comparison

* **REQ-8.1:** The app SHALL provide a **Compare** view showing two schemes side by side, listing only settings whose AC or DC values differ.
* **REQ-8.2:** Comparison SHALL reuse the shared setting catalog and two `SchemeValues` sets (ADR-012). It SHALL NOT trigger a second full enumeration.
* **REQ-8.3:** The view SHALL offer a one-click "compare against base template" for any custom scheme, answering "what have I actually changed?".
* **REQ-8.4:** Each differing row SHALL offer **Copy value from the other scheme**, so a comparison can be resolved without leaving the view.
* **REQ-8.5:** The CLI SHALL provide `compare --scheme A --scheme B`, with `--json` emitting a machine-readable diff.

### Requirement 9: Defaults, Deviation and Per-Setting Reset

* **REQ-9.1:** The app SHALL read each setting's default via `PowerReadACDefaultIndex` / `PowerReadDCDefaultIndex`, keyed by **the scheme's personality**, not its GUID ([[Win32 API Reference]] §6.10).
* **REQ-9.2:** Settings whose current value deviates from that default SHALL carry a visible **Modified** badge.
* **REQ-9.3:** Each such setting SHALL offer **Reset to default**, restoring AC and DC independently.

  > **Why:** without this, the only recovery is `PowerRestoreDefaultPowerSchemes`, which deletes every custom scheme on the machine. A user who broke one sleep timeout must never be routed to that.

* **REQ-9.4:** A **Show only modified** filter SHALL be available, composing with search and category filters.
* **REQ-9.5:** Settings with no defined default SHALL show no badge and SHALL disable the reset control. `ERROR_FILE_NOT_FOUND` here is not an error.
* **REQ-9.6:** The CLI SHALL provide `reset-setting --scheme S --setting G [--ac] [--dc]` and `list-settings --modified-only`.

### Requirement 10: Navigation & Discoverability

* **REQ-10.1:** `Ctrl+K` SHALL open a **command palette** offering fuzzy search across settings, schemes, categories, and app commands, with keyboard-only operation.
* **REQ-10.2:** Search SHALL additionally match **subgroup names** and **possible-value names**, so searching "Aggressive" finds the setting offering that choice (extends REQ-5.1).
* **REQ-10.3:** An **Essentials** view SHALL present a curated starter list from `data/essentials.json`. A missing or malformed file SHALL hide the view, never block startup.
* **REQ-10.4:** Users SHALL be able to pin settings as **favorites**, persisted in `ui-state.json` and surfaced as a sidebar category.
* **REQ-10.5:** Each setting SHALL offer **Copy GUID** and **Copy `powercfg` command**, producing text ready to paste into a script or forum post.
* **REQ-10.6:** Settings listed in `data/reboot_required.json` SHALL carry an indicator that the change takes effect after a reboot or power-source change.
* **REQ-10.7:** Where `data/doc_links.json` supplies a Microsoft Learn URL, the setting SHALL expose it as **copyable text**. The app SHALL NOT open it — there is no network capability and no browser invocation (NFR-4).

### Requirement 11: Undo & Bulk Editing

* **REQ-11.1:** `Ctrl+Z` SHALL revert the most recent value change by re-writing the previous value. **Single level only** — no history is persisted, so ADR-005 is unaffected.
* **REQ-11.2:** Undo SHALL be unavailable after a scheme switch, refresh, or import, since the prior value may no longer be meaningful.
* **REQ-11.3:** Setting cards SHALL offer a **link AC/DC** toggle applying one value to both rails at once.
* **REQ-11.4:** The app SHALL support applying a single setting's value across **all custom schemes** in one action, with a confirmation listing every scheme affected.

### Requirement 12: Export Formats

* **REQ-12.1:** Export SHALL offer three formats: **JSON preset** (round-trips through this app), **`powercfg` script** (`.ps1`/`.cmd`, portable automation), and **Markdown summary** (documentation).
* **REQ-12.2:** Generated scripts SHALL contain only validated literal GUIDs and integers, carry a provenance header, and sanitise any user-supplied name (ADR-013).
* **REQ-12.3:** The app SHALL NOT execute a generated script. It writes text only.
* **REQ-12.4:** A **machine backup bundle** SHALL export all custom schemes plus full visibility state in one file, restorable on another machine.

### Requirement 13: Appearance & Portability

* **REQ-13.1:** The app SHALL support **Light**, **Dark**, and **System** appearance, defaulting to System via `darkdetect`. The choice persists in `ui-state.json`.
* **REQ-13.2:** Both palettes SHALL meet WCAG AA contrast ([[CLI and UX Interface Specification]] §1.1).
* **REQ-13.3:** When `portable.txt` sits beside the executable **and that directory is writable**, state, logs, and backups SHALL be written to `data/` next to the binary (ADR-014). Otherwise `%LOCALAPPDATA%` is used.
* **REQ-13.4:** A read-only or unwritable portable directory SHALL fall back silently to `%LOCALAPPDATA%`, never crash.

### Requirement 14: Single Instance

* **REQ-14.1:** A second GUI launch SHALL bring the existing window to the foreground and exit `0`, rather than opening a second window ([[Win32 API Reference]] §6.11).
* **REQ-14.2:** The guard SHALL be session-scoped (`Local\` mutex), so Fast User Switching and Remote Desktop sessions each get their own instance.
* **REQ-14.3:** CLI subcommands and elevated-helper mode SHALL bypass the guard entirely and remain runnable in parallel.

### Requirement 15: CLI Automation Support

* **REQ-15.1:** `--dry-run` SHALL be accepted by **every** mutating subcommand, printing the intended change and exiting `0` without writing.
* **REQ-15.2:** A `watch` subcommand SHALL poll settings at a configurable interval and print changes as they occur, for diagnosing OEM utilities that alter settings in the background.
* **REQ-15.3:** `watch` SHALL be read-only and interruptible with `Ctrl+C`, exiting `0`.

---

## 7. Non-Functional Requirements

* **NFR-1 — Responsiveness:** The UI main thread SHALL never block for more than 16 ms. All enumeration and Win32 I/O runs on a worker thread (ADR-003). **This is the only non-negotiable performance target.**
* **NFR-2 — Startup:** Onedir under 800 ms; onefile under 3 s, cold. See [[Test Plan and Benchmark Targets]] §3.
* **NFR-2b — Scheme switching:** Under 150 ms, by re-reading only per-scheme values against the shared catalog (ADR-012).
* **NFR-2c — Idle cost:** The queue-drain loop SHALL run only while a worker is active. Idle CPU SHALL be indistinguishable from zero.
* **NFR-3 — Privilege:** The app SHALL run as Standard User and SHALL NOT require elevation for launch, enumeration, scheme CRUD, or AC/DC edits.
* **NFR-4 — Isolation:** The app SHALL make no network connections and SHALL contain no networking libraries. Enforced in CI.
* **NFR-5 — Resilience:** A single unreadable setting SHALL NOT abort enumeration ([[Error Handling and Logging]] §5).
* **NFR-6 — Portability:** The onefile artifact SHALL run on a machine with no Python installed and SHALL leave behind only its log and UI-state files.
* **NFR-7 — Localization:** Setting names and descriptions SHALL be displayed in the OS language as returned by Windows. Application chrome is English-only in v1.0.

---

## 8. Known Limitations

Stated here so they are decisions rather than discoveries:

1. **No screen-reader support.** CustomTkinter widgets are Canvas-drawn and invisible to UI Automation (ADR-002).
2. **Visibility changes are global**, not per-scheme, and are reset by Windows feature updates (ADR-006).
3. **Exports are JSON, not `.pow`**, and are not consumable by `powercfg` (ADR-007).
4. **Power mode overlay is read-only** (ADR-009).
5. **Windows ARM64 runs under x64 emulation.** No native ARM64 release ([[Build Packaging and Release]] §2).
6. **Visibility writes depend on undocumented registry behaviour** (`Attributes = 2`), the only mechanism that actually works (ADR-006).
