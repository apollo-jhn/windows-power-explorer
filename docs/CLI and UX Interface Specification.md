# CLI and UX Interface Specification

* **Document Version:** 2.0.0
* **Target Stack:** Python 3.10+, `ctypes`, `customtkinter` 6.0.0, `argparse`
* **Related Documents:** [[Index]], [[Product Requirements Document]], [[Technical Design Document]], [[Win32 API Reference]], [[Data Flow and Configuration Schema]], [[Error Handling and Logging]], [[Design Specification]]

---

## 1. User Experience (UX) & Graphical Interface Specification

### 1.1 Visual Theme & Color Palette

Three appearance modes — **Light**, **Dark**, and **System** — with System the default, resolved through `darkdetect` (already a dependency). The choice persists in `ui-state.json` (REQ-13.1).

CustomTkinter accepts `(light, dark)` tuples for every color property, so both palettes are declared once in `ui/theme.py` rather than branching at each widget.

| UI Element | Purpose | Light | Dark |
| :--- | :--- | :--- | :--- |
| **App Background** | Primary window backdrop | `#F8FAFC` | `#1A1B26` |
| **Surface Cards** | Container cards & sidebar | `#FFFFFF` | `#24283B` |
| **Primary Accent** | Active scheme badge, sliders, toggles | `#0891B2` | `#06B6D4` |
| **Success Accent** | Applied confirmations | `#059669` | `#10B981` |
| **Text Primary** | Headers, setting titles | `#0F172A` | `#FFFFFF` |
| **Text Secondary** | Subtitles, descriptions, GUIDs | `#475569` | `#9CA3AF` |
| **Border / Divider** | Component boundaries | `#E2E8F0` | `#374151` |
| **Modified Badge** | Setting deviates from default | `#7C3AED` | `#A78BFA` |
| **Warning Accent** | Hazard notes, policy-locked, reboot-required | `#B45309` | `#F59E0B` |
| **Danger Accent** | Delete scheme, restore defaults | `#DC2626` | `#EF4444` |

**Contrast requirement:** every text/background pair meets **WCAG AA** (4.5:1 body, 3:1 large text) **in both palettes**. `#9CA3AF` on `#24283B` measures ≈ 6.2:1; `#475569` on `#FFFFFF` ≈ 8.6:1. Any new pair is checked before use — this is a testable gate, unlike screen-reader support (§1.4).

**Never encode meaning in color alone.** The Modified badge carries a label, policy locks carry a padlock glyph, and hazard notes carry text. Color is reinforcement, not the signal.

---

### 1.2 Desktop Window Layout & Breakpoints

* **Default Window Size:** `1150 x 720` (centred on first launch; subsequently restored from `ui-state.json`).
* **Minimum Window Size:** `920 x 600`.
* **Layout Structure:** 2-column split view (fixed sidebar + flexible main content area).

```text
+------------------------------------------------------------------------------------+
|  ⚡ Windows Power Explorer   [🔍 Search... (Ctrl+F)]  [Modified only] [+ New Scheme] |  Header
+------------------------------+-----------------------------------------------------+
|  POWER SCHEMES               |  Processor Power Management                         |
|  🟢 My Custom Gaming Plan    |  -------------------------------------------------  |
|     Balanced                 |                                                     |
|     High Performance         |  Processor performance boost mode      ● Modified   |
|                              |  Controls CPU Turbo Boost behavior.      [Reset]    |
|  CATEGORIES                  |  AC (Plugged In):  [ Aggressive          v ]        |
|  ★ Favorites                 |  DC (On Battery):  [ Disabled            v ]  🔗    |
|  ✦ Essentials                |  -------------------------------------------------  |
|  ⚡ CPU & Performance        |  Minimum Processor State                            |
|  🎮 GPU & PCIe               |  AC: [====|============== 5%]                       |
|  🔋 Battery & Sleep          |  DC: [========|========== 5%]                       |
|  🖥️ Display                  |  -------------------------------------------------  |
|  🔌 Storage & Devices        |  System unattended sleep timeout       🔒 Managed   |
|                              |  Managed by your organisation.                      |
|  TOOLS                       |  -------------------------------------------------  |
|  ⇄ Compare Schemes           |  Hibernate after                       ↻ Reboot    |
|  👁 Control Panel Visibility |  Takes effect after restarting.                     |
|  ♻ Restore Defaults          |                                                     |
+------------------------------+-----------------------------------------------------+
| "My Custom Gaming Plan" active · Power mode: Best performance ⓘ         | System OK |  Footer
+------------------------------------------------------------------------------------+
```

Elements worth noting: the footer's **power mode indicator** (REQ-7.1); the **TOOLS** section holding the global visibility manager, deliberately outside setting cards (ADR-006); the **● Modified** badge with its per-setting **[Reset]** (REQ-9.2, REQ-9.3); the **🔗** link-rails toggle (REQ-11.3); **★ Favorites** and **✦ Essentials** pseudo-categories (REQ-10.3, REQ-10.4); and the **↻ Reboot** indicator (REQ-10.6).

On a desktop with no battery the **DC row is omitted entirely**, not shown empty — reclaiming the width for names and descriptions (REQ-2.6).

Right-clicking any setting offers **Copy GUID**, **Copy `powercfg` command**, **Pin to favorites**, and, where known, **Copy documentation link** (REQ-10.5, REQ-10.7).

---

### 1.3 `customtkinter` Component Tree

```text
customtkinter.CTk (Main App Window)
├── CTkFrame (Top Header Bar)
│   ├── CTkLabel (App Logo & Title)
│   ├── CTkEntry (Global Search Input)
│   ├── CTkSwitch ("Modified only" filter)
│   └── CTkButton ("+ Create Custom Scheme")
├── CTkFrame (Main Body Split Container)
│   ├── CTkScrollableFrame (Left Navigation Sidebar)
│   │   ├── CTkLabel ("Power Schemes") + CTkButton (per scheme)
│   │   ├── CTkLabel ("Categories")    + CTkButton (Favorites, Essentials, per subgroup)
│   │   └── CTkLabel ("Tools")         + CTkButton (Compare, Visibility, Restore Defaults)
│   └── CTkScrollableFrame (Right Content Area — see [[Technical Design Document]] §7)
│       └── CTkFrame (SettingCardWidget — recycled)
│           ├── CTkLabel (Setting Name)  + CTkLabel (Modified badge)
│           ├── CTkLabel (Description)   + CTkButton ("Reset")
│           ├── CTkFrame (AC / DC Value Controls)
│           │   ├── CTkSlider / CTkOptionMenu / CTkSwitch (AC)
│           │   ├── CTkSlider / CTkOptionMenu / CTkSwitch (DC — omitted if no battery)
│           │   └── CTkButton (link-rails toggle)
│           └── CTkLabel (hazard note / policy-locked / reboot-required, when applicable)
└── CTkFrame (Bottom Status Footer)
    ├── CTkLabel (Status message / active scheme)
    └── CTkLabel (Power mode overlay indicator)

CTkToplevel (Command Palette — Ctrl+K)
├── CTkEntry (fuzzy query)
└── CTkScrollableFrame (ranked results: settings, schemes, categories, commands)
```

Two views replace the right content area when selected:

* **Control Panel Visibility** — `VisibilityRowWidget` rows, a persistent system-wide banner, and an **Apply** bar.
* **Compare Schemes** — two scheme selectors and `DiffRowWidget` rows showing only differing settings, each with a **Copy from other scheme** action (REQ-8.4).

> [!NOTE]
> `CTkSwitch` no longer appears inside `SettingCardWidget`. Visibility moved to its own
> view in v2.0.0 because the attribute is global rather than per-scheme (ADR-006).

---

### 1.4 Keyboard Navigation

| Shortcut | Action | Scope |
| :--- | :--- | :--- |
| `Ctrl + F` | Focus the search input | Global |
| `Escape` | Clear search filter / close active modal | Global |
| `Ctrl + N` | Open "Create Custom Scheme" modal | Global |
| `Ctrl + R` | Refresh scheme list and re-enumerate settings | Global |
| `Ctrl + K` | Open the command palette — fuzzy jump to any setting, scheme, or command | Global |
| `Ctrl + E` | Export the selected scheme (format chosen in the dialog) | Global |
| `Ctrl + I` | Import a preset or `.pow` file | Global |
| `Ctrl + D` | Compare the selected scheme against its base template | Global |
| `Ctrl + Z` | Undo the last value change (single level) | Global |
| `Ctrl + M` | Toggle "show only modified" filter | Global |
| `F1` | Open the log folder | Global |
| `Tab` / `Shift + Tab` | Move focus forward / backward | UI Controls |
| `Space` | Toggle the focused switch / activate the focused button | UI Controls |
| `Arrow keys` | Adjust the focused slider by one increment | UI Controls |
| `Enter` | Confirm the focused dialog action | Dialogs |

**Focus requirements:** every interactive control must show a visible focus ring against `#1A1B26`; tab order follows visual order; modals trap focus (`grab_set`) and restore it to the invoking control on close.

> [!WARNING]
> **Accessibility limitation — no screen reader support.**
> CustomTkinter widgets are drawn on a `tkinter.Canvas` and expose **no UI Automation
> tree**. Narrator, NVDA, and JAWS cannot see or announce this application's controls.
> Keyboard navigation and WCAG AA contrast are supported and tested; assistive
> technology is not.
>
> This is a permanent consequence of the GUI framework choice (ADR-002) and cannot be
> fixed without replacing the entire UI layer. It is stated here rather than omitted so
> that users who need a screen reader are not left to discover it themselves. Users
> requiring accessible power configuration should use the built-in Windows Settings app
> or `powercfg.exe`, both of which are fully accessible.

---

## 2. Command-Line Interface (CLI) Specification

A headless CLI built into `main.py` with `argparse`, at **full feature parity with the GUI**. Anything the GUI can do is scriptable.

> [!NOTE]
> The shipped executable is windowed (`console=False`), so it reattaches to the parent
> console when a subcommand is present. See [[Build Packaging and Release]] §4.1. Output
> is identical whether run as `python main.py` or `WindowsPowerExplorer.exe`.

### 2.1 Syntax

```bash
WindowsPowerExplorer.exe [GLOBAL_FLAGS] <SUBCOMMAND> [ARGS]
```

Launching with no subcommand starts the GUI.

#### Global Flags
* `--json` / `-j`: emit structured JSON on stdout. Uses the uniform envelope in §2.4.
* `--verbose` / `-v`: `DEBUG` logging, including every FFI call, GUID, and return code.
* `--yes` / `-y`: assume yes for confirmations. **Does not bypass UAC**, and is refused by `restore-defaults`, which always requires its typed phrase.
* `--dry-run` / `-n`: accepted by **every** mutating subcommand. Prints the intended change and exits `0` without writing (REQ-15.1).
* `--version`: print version and exit `0`.

`--headless` from v1.0.0 is **removed** — supplying a subcommand is itself the headless signal, and the flag was ambiguous.

CLI subcommands and elevated-helper mode **bypass the single-instance guard** and remain runnable in parallel with a running GUI and with each other (REQ-14.3).

---

### 2.2 Subcommands

Schemes may be identified by GUID or exact friendly name throughout. Where a name is ambiguous, the command fails with exit code `2` and lists the matches.

#### Discovery

```bash
# List all power schemes
WindowsPowerExplorer.exe list-schemes

# List settings, optionally filtered
WindowsPowerExplorer.exe list-settings --scheme "Balanced" [--category cpu] [--search boost] [--hidden-only]

# Show one setting in full: bounds, choices, AC/DC, visibility, policy state
WindowsPowerExplorer.exe show-setting --scheme "Balanced" --setting be337238-0d82-4146-a960-4f3749d470c7
```

`list-schemes` human output:

```text
  Active  GUID                                  Name
  ------  ----                                  ----
* [*]     381b4222-f694-41f0-9685-ff5bb260df2e  Balanced
          8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  High Performance
          a1841308-3541-4fab-bc81-f71556f20b4a  Power Saver
          f4e6f13e-4efd-435f-adb4-fc42d20a1537  My Custom Gaming Plan

Power mode overlay: Best performance
```

#### Scheme Lifecycle

```bash
WindowsPowerExplorer.exe create-scheme --base HighPerformance --name "Esports Ultra" --desc "Max GPU & CPU state"
WindowsPowerExplorer.exe rename-scheme --scheme "Esports Ultra" --name "Esports Pro" [--desc "..."]
WindowsPowerExplorer.exe delete-scheme --scheme "Esports Pro" [--yes]
WindowsPowerExplorer.exe set-active    --scheme "Esports Pro"
```

`create-scheme --base` accepts a friendly alias (`Balanced`, `HighPerformance`, `PowerSaver`, `UltimatePerformance`) or any GUID. **Aliases resolve against schemes present on this machine** — an alias for an absent scheme fails with exit code `2` rather than a confusing Win32 error.

#### Value Editing

```bash
WindowsPowerExplorer.exe edit-setting \
  --scheme "Esports Pro" \
  --setting be337238-0d82-4146-a960-4f3749d470c7 \
  --ac 0 --dc 0
```

`--ac` and `--dc` are independent; supplying neither is an error. Values are bounds-checked before the write. `PowerSetActiveScheme` is invoked only when the edited scheme is the active one (REQ-2.3).

#### Visibility *(requires Administrator)*

```bash
WindowsPowerExplorer.exe unhide-all            # Attributes = 2 everywhere
WindowsPowerExplorer.exe unhide   --setting <GUID> [--subgroup <GUID>]
WindowsPowerExplorer.exe hide     --setting <GUID> [--subgroup <GUID>]
WindowsPowerExplorer.exe restore-visibility    # replay the recorded prior state
```

> [!NOTE]
> Without Administrator rights these commands exit `5` (`ERR_ACCESS_DENIED`) with a hint
> to re-run from an elevated prompt. **The CLI does not raise a UAC prompt** — a
> consent dialog appearing mid-script would break unattended automation. This differs
> deliberately from the GUI, which does prompt.

#### Comparison & Defaults

```bash
# Diff two schemes — only settings whose AC or DC values differ
WindowsPowerExplorer.exe compare --scheme "Balanced" --scheme "Esports Pro"

# Diff a custom scheme against the base template it was cloned from
WindowsPowerExplorer.exe compare --scheme "Esports Pro" --against-base

# Only settings deviating from the Windows default for this scheme's personality
WindowsPowerExplorer.exe list-settings --scheme "Esports Pro" --modified-only

# Reset one setting to its default; --ac / --dc independently, both if neither given
WindowsPowerExplorer.exe reset-setting --scheme "Esports Pro" --setting <GUID> [--ac] [--dc]
```

`compare` human output:

```text
Balanced  →  Esports Pro          (2 of 147 settings differ)

  Processor performance boost mode           AC: Enabled (2) → Aggressive (3)
                                             DC: Enabled (2) → Disabled  (0)
  Maximum processor state                    AC: 100%       → 100%   (same)
                                             DC:  80%       →  95%
```

`--json` emits a structured diff with `before`/`after` per rail, suitable for feeding into a change-review pipeline.

Defaults are resolved against the scheme's **personality**, not its GUID ([[Win32 API Reference]] §6.10). Settings with no defined default are reported as `"default": null` and are not counted as modified.

#### Presets & Export

```bash
WindowsPowerExplorer.exe export --scheme "Esports Pro" --out "C:\presets\esports.json"
WindowsPowerExplorer.exe export --scheme "Esports Pro" --format powercfg --out "C:\presets\esports.ps1"
WindowsPowerExplorer.exe export --scheme "Esports Pro" --format markdown --out "C:\docs\esports.md"

WindowsPowerExplorer.exe import --in "C:\presets\esports.json" [--name "Imported Plan"] [--dry-run]

# Whole-machine bundle: every custom scheme plus full visibility state
WindowsPowerExplorer.exe backup  --out "C:\backups\workstation.json"
WindowsPowerExplorer.exe restore --in  "C:\backups\workstation.json" [--dry-run]
```

`--format` accepts `json` (default), `powercfg`, and `markdown` (REQ-12.1). There is no `.pow` export API (ADR-007); the `powercfg` script is the portable-automation substitute (ADR-013). `import` accepts `.json` and `.pow`.

> [!NOTE]
> **`export --format powercfg` writes a script; it never runs one.** The output is plain
> text containing only validated literal GUIDs and integers. Review it before executing.

#### Monitoring

```bash
# Print settings as they change. Read-only; Ctrl+C exits 0.
WindowsPowerExplorer.exe watch [--interval 2] [--scheme "Balanced"] [--setting <GUID>]
```

Useful for catching an OEM utility or scheduled task altering settings behind your back — a common cause of "my power plan keeps resetting". Output is one line per observed change with a timestamp.

#### Recovery

```bash
WindowsPowerExplorer.exe restore-defaults --confirm "DELETE MY PLANS" [--backup-dir <path>]
```

Requires Administrator and the literal `--confirm` phrase. Backs up all custom schemes first and **aborts if the backup fails**. `--yes` does not satisfy this. See [[Recovery and Destructive Operations]] §3.

---

### 2.3 Exit Codes

| Exit Code | Symbol | Meaning |
| :--- | :--- | :--- |
| `0` | `SUCCESS` | Operation completed successfully. |
| `1` | `ERR_GENERAL` | General execution failure or invalid CLI argument. |
| `2` | `ERR_SCHEME_NOT_FOUND` | Scheme GUID or name does not exist, or the name is ambiguous. |
| `3` | `ERR_SETTING_NOT_FOUND` | Setting GUID does not exist in the given subgroup. |
| `4` | `ERR_VALUE_OUT_OF_BOUNDS` | Value violates the setting's min/max/increment. |
| `5` | `ERR_ACCESS_DENIED` | Requires elevated Administrator privileges. |
| `6` | `ERR_POLICY_LOCKED` | A Group Policy override forbids modifying this setting. Elevation will not help. |
| `7` | `ERR_ELEVATION_DECLINED` | User dismissed the UAC prompt (GUI-initiated flows only). |
| `8` | `ERR_PRESET_INVALID` | Preset file failed schema or semantic validation. |
| `9` | `ERR_IO` | Could not read or write a preset, backup, or log file. |
| `10` | `ERR_UNSUPPORTED` | Operation unsupported on this OS build or hardware. |

Codes `6`–`10` are new in v2.0.0. Code `6` in particular must be distinguishable from `5`: retrying elevated fixes `5` and never fixes `6`.

---

### 2.4 JSON Output Envelope

Every `--json` invocation emits exactly one object on stdout. `stderr` stays empty so scripts have one thing to parse.

**Success:**

```json
{
  "ok": true,
  "data": [
    {
      "guid": "381b4222-f694-41f0-9685-ff5bb260df2e",
      "name": "Balanced",
      "is_active": true,
      "is_base_default": true
    },
    {
      "guid": "f4e6f13e-4efd-435f-adb4-fc42d20a1537",
      "name": "My Custom Gaming Plan",
      "is_active": false,
      "is_base_default": false
    }
  ]
}
```

**Failure:**

```json
{
  "ok": false,
  "error": {
    "code": "ERR_SCHEME_NOT_FOUND",
    "exit_code": 2,
    "message": "scheme not found: 'Esports Ultr'",
    "win32_code": null
  }
}
```

`win32_code` carries the raw DWORD when the failure came from `powrprof.dll`, `null` otherwise. The envelope is identical across all subcommands, so a script can branch on `.ok` before touching `.data`.
