# Design Specification
*(Python 3.10+ | `ctypes` | `customtkinter` 6.0.0)*

* **Document Version:** 2.0.0
* **Related Documents:** [[Index]], [[Product Requirements Document]], [[Technical Design Document]], [[CLI and UX Interface Specification]], [[Architecture Decision Records]]

---

## 🎨 Visual Interface & Concept

**Windows Power Explorer** is a focused, modern replacement for PowerSettingsExplorer written in **Python**. It uses **`customtkinter`** for a native dark-mode GUI and **`ctypes`** for Win32 `PowrProf.dll` interop.

It eliminates raw GUID clutter and provides direct access to **all hidden Windows power settings**, per-profile AC/DC editing, and custom power scheme creation derived from existing schemes.

---

![[ui_mockup.jpg]]

---

## 📂 Project Architecture

The canonical module tree lives in [[Product Requirements Document]] §4.2. Summarised:

```text
windows_power_explorer/
├── main.py          # Entry: GUI, CLI dispatch, elevated-helper mode
├── core/            # Bindings, power manager, visibility, overlay, controller,
│                    # presets, elevation, models, errors, ui_state
├── cli/             # argparse parser & subcommand implementations
├── ui/
│   ├── app.py sidebar.py search_bar.py status_bar.py
│   ├── components/  # setting_card.py, visibility_row.py
│   ├── views/       # visibility_view.py
│   └── dialogs/     # base.py, create_scheme_dialog.py, elevation_dialog.py
├── schema/          # power_preset.schema.json
└── assets/          # Icons & themes
```

---

## 🎯 Core Feature Specifications

### 1. Scheme Builder & Management
* **Create custom profiles:** modal dialog (`CTkToplevel`) offering schemes **discovered live** on this machine to clone via `PowerDuplicateScheme`. Absent base schemes are not offered — on Modern Standby machines only *Balanced* may exist (REQ-1.1).
* **Rename & customize metadata:** custom names and descriptions via `PowerWriteFriendlyName` / `PowerWriteDescription`.
* **Personality matching:** cloning sets the power plan personality (`245d8541-…`) to match the base template, and surfaces it as a prominent card. Without this, a scheme cloned from Balanced behaves like Balanced no matter what else is changed (REQ-1.4).
* **Profile management:** activate (`PowerSetActiveScheme`), delete (`PowerDeleteScheme`, typed-name confirmation, built-ins protected), export to JSON, import JSON or `.pow`.

### 2. Setting Explorer
* **Deep enumeration:** all power settings across all subgroups via `PowerEnumerate`, on a worker thread with progressive rendering.
* **Category & search filtering:** group by subgroup (CPU, GPU, Display, Sleep, Storage) or search by keyword, name, or GUID via `CTkEntry`.
* **Honest degradation:** settings with missing metadata show their GUID and stay editable; settings with unreadable bounds render read-only; Group-Policy-locked settings render disabled with an explanation.

### 3. Per-Profile AC (Plugged In) & DC (Battery) Tuning
* **Independent AC / DC controls** for whichever scheme is selected.
* **Interactive widgets:** `CTkSlider` for ranges, `CTkOptionMenu` for enums, `CTkSwitch` for booleans — inferred from live metadata (REQ-2.4).
* **Hazard warnings, not blocks:** values with surprising consequences carry a muted inline note. Every value Windows accepts is permitted.
* **Battery-less machines** render the DC column as unavailable rather than showing misleading zeroes.

### 4. Control Panel Visibility Manager *(separate view)*

> [!IMPORTANT]
> **This is deliberately not part of the setting card.** Visibility is stored globally under
> `HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerSettings`, independent of any scheme
> and shared by every user on the machine. A switch inside a per-scheme card would tell
> users it applies to that scheme alone — it does not (ADR-006).

* A dedicated **Control Panel Visibility** view, reached from the sidebar, listing every setting with a `CTkSwitch`.
* A persistent banner: *"Changes here apply to every power plan and every user on this computer, and need Administrator permission."*
* **Batched application.** Toggles accumulate as pending changes; a single **Apply** raises one UAC prompt via the elevated helper (ADR-008).
* **Show All** and **Restore Control Panel Defaults** bulk actions, the latter replaying the recorded prior state.
* Re-apply prompt on launch when Windows has reset attributes after a feature update.

### 5. Scheme Comparison *(separate view)*
* **Side-by-side diff** of any two schemes, listing only settings whose AC or DC values differ. Answers the question this whole category of tool exists for: *what is actually different?*
* **Compare against base template** in one click for any custom scheme — the fastest answer to "what have I changed?", and a better audit trail than reading the log.
* **Copy value from the other scheme** on each row, so a comparison resolves in place.
* Costs one extra `SchemeValues` load against the shared catalog (ADR-012) — no second enumeration.

### 6. Defaults & Per-Setting Reset
* **Modified badge** on every setting deviating from the Windows default for that scheme's *personality* ([[Win32 API Reference]] §6.10).
* **Reset to default** per setting, AC and DC independently. This is the lightweight recovery tier that keeps users away from the destructive one — before this existed, the only remedy for one bad sleep timeout was deleting every custom scheme on the machine.
* **Show only modified** filter, composing with search and category.
* Settings with no defined default show no badge and disable the reset control.

### 7. Navigation & Discoverability
* **Command palette** (`Ctrl+K`): fuzzy jump across settings, schemes, categories, and commands. Keyboard-only, and the fastest path through a list of 150 items.
* **Essentials** view: a curated starter list for people who want the fifteen settings that matter, not all of them.
* **Favorites**: user-pinned settings surfaced as a sidebar category, persisted in `ui-state.json`.
* **Copy GUID** / **Copy `powercfg` command** on every setting — turns the app into a learning tool and the obvious thing to keep open while following a guide.
* **Reboot-required** and **documentation link** indicators where known. Links are copyable text; the app never opens a browser (NFR-4).

### 8. Export Formats
Three formats, chosen in the export dialog:

| Format | For |
| :--- | :--- |
| **JSON preset** | Round-tripping through this app; the only format `import` reads back |
| **`powercfg` script** (`.ps1` / `.cmd`) | Portable automation — reviewable, diffable, runnable anywhere without this app (ADR-013) |
| **Markdown summary** | Documentation and change review |

A **machine backup bundle** exports all custom schemes plus full visibility state as one file for restoring on another machine.

### 9. Recovery
* **Restore Windows Default Power Schemes** with mandatory automatic backup, an explicit list of what will be deleted, and typed-phrase confirmation. Full flow in [[Recovery and Destructive Operations]] §3.
* **Single-level undo** (`Ctrl+Z`) on the last value change — enough to make experimenting feel safe without a persisted history that would drift from the registry.

---

## 🌗 Appearance & Portability

* **Light / Dark / System** appearance, System by default via `darkdetect`. Both palettes meet WCAG AA in every text pair ([[CLI and UX Interface Specification]] §1.1), and no meaning is ever carried by color alone.
* **Portable mode**: a `portable.txt` beside the executable redirects state, logs, and backups to a `data/` folder next to the binary (ADR-014). A read-only location falls back silently to `%LOCALAPPDATA%` rather than failing to start.
* **Single instance**: a second launch activates the existing window instead of opening a rival one that would show contradictory state.

---

## 🧩 In-House Dialog Components (ADR-011)

CustomTkinter 6.0.0 ships only `CTkInputDialog` — there is no message box or toast. `ui/dialogs/base.py` provides:

| Component | Purpose |
| :--- | :--- |
| `ConfirmDialog` | Title, body, optional typed-phrase gate, optional secondary action ("Export first"), destructive styling |
| `ElevationDialog` | Explains which changes need Administrator and what will happen, before the UAC prompt appears |
| Status-bar toast | Transient text in the footer, auto-clearing after 4 s — not a floating window |

**Modal behaviour every dialog must implement:** `grab_set()` for true modality, centred on the parent, `Escape` cancels, window-close cancels, and **the safe action holds initial focus** so a stray `Enter` cannot confirm a destructive operation.

Floating toast windows are deliberately avoided — they steal focus, misbehave on multi-monitor setups, and add window management for no benefit over footer text.

---

## 🖼️ Rendering Notes

Setting cards are **virtualised**: only cards intersecting the viewport are constructed, and scrolling recycles widgets ([[Technical Design Document]] §6). CTk widgets are Canvas-drawn and comparatively expensive, so realising 150 cards at once is the difference between a snappy list and a visible stall. Search filtering re-drives the virtual list from the data model rather than creating or destroying widgets per keystroke.
