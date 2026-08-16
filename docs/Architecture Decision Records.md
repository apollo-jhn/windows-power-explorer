# Architecture Decision Records (ADRs)

* **Status:** Approved
* **Document Version:** 2.0.0
* **Related Documents:** [[Index]], [[Product Requirements Document]], [[Technical Design Document]], [[Win32 API Reference]], [[Design Specification]]

---

## Record Index

1. [ADR-001: Use Python 3.10+ with `ctypes` for Win32 API Interop](#adr-001-use-python-310-with-ctypes-for-win32-api-interop)
2. [ADR-002: Select `customtkinter` as Primary GUI Framework](#adr-002-select-customtkinter-as-primary-gui-framework)
3. [ADR-003: Use a Worker Thread with a Result Queue for Win32 Enumeration](#adr-003-use-a-worker-thread-with-a-result-queue-for-win32-enumeration)
4. [ADR-004: Least-Privilege Execution with On-Demand Elevation](#adr-004-least-privilege-execution-with-on-demand-elevation)
5. [ADR-005: OS Registry as Single Source of Truth for Power Data](#adr-005-os-registry-as-single-source-of-truth-for-power-data)
6. [ADR-006: Write Visibility Attributes Directly to the Registry](#adr-006-write-visibility-attributes-directly-to-the-registry)
7. [ADR-007: JSON-Only Export; No `powercfg.exe` Shell-Out](#adr-007-json-only-export-no-powercfgexe-shell-out)
8. [ADR-008: Elevated Helper Process Rather Than Relaunching the App](#adr-008-elevated-helper-process-rather-than-relaunching-the-app)
9. [ADR-009: Read-Only Awareness of Windows 11 Power Mode Overlays](#adr-009-read-only-awareness-of-windows-11-power-mode-overlays)
10. [ADR-010: Ship Both Onefile and Onedir Artifacts](#adr-010-ship-both-onefile-and-onedir-artifacts)
11. [ADR-011: Build Dialogs In-House on `CTkToplevel`](#adr-011-build-dialogs-in-house-on-ctktoplevel)
12. [ADR-012: Two-Phase Load — Setting Catalog Separate from Scheme Values](#adr-012-two-phase-load--setting-catalog-separate-from-scheme-values)
13. [ADR-013: `powercfg` Script as a Third Export Format](#adr-013-powercfg-script-as-a-third-export-format)
14. [ADR-014: Portable Mode via a Sentinel File](#adr-014-portable-mode-via-a-sentinel-file)

---

### ADR-001: Use Python 3.10+ with `ctypes` for Win32 API Interop

**Status:** Accepted

#### Context
The core functionality requires invoking native Windows C APIs inside `PowrProf.dll` (`PowerEnumerate`, `PowerDuplicateScheme`, `PowerWriteACValueIndex`, `PowerWriteSettingAttributes`). We evaluated three implementation paths:
1. C# / .NET 8 (WinUI 3 or WPF with P/Invoke)
2. C++20 with native Win32 API / WinUI
3. Python 3.10+ using standard library `ctypes`

#### Decision
Build in **Python 3.10+** using the built-in **`ctypes`** library for all C-FFI interactions with `PowrProf.dll`.

#### Rationale
* **Zero compilation dependency:** `ctypes` calls C functions directly without C++ compilers, MSBuild toolchains, or native extension builds.
* **Rapid iteration:** clean memory abstractions, built-in Unicode handling, fast edit-test cycles.
* **Single-executable portability:** PyInstaller packages the codebase into a self-contained `.exe` with no Python or .NET runtime prerequisite.

#### Consequences
* **Positive:** Clean codebase, no native build setup.
* **Negative:** C struct definitions and pointer lifetimes must be hand-written and are easy to get subtly wrong. **This is the project's largest correctness risk** — a wrong `argtypes` declaration fails silently rather than loudly. Mitigated by making [[Win32 API Reference]] the single authoritative binding source and by import-time binding verification.
* **Negative:** Startup time and memory footprint are bounded below by the CPython + Tcl/Tk runtime, which forced the benchmark revision in [[Test Plan and Benchmark Targets]] §3 and the dual-artifact decision in ADR-010.

---

### ADR-002: Select `customtkinter` as Primary GUI Framework

**Status:** Accepted

#### Context
We required a lightweight desktop GUI framework delivering a modern, dark-themed aesthetic matching Windows 11 Fluent design. We evaluated:
1. Standard `tkinter` (dated 1990s visual style)
2. `PyQt6` / `PySide6` (heavy binary size ~100MB+, licensing constraints)
3. `customtkinter` (modern dark-mode wrapper built on `tkinter`)

#### Decision
Use **`customtkinter` 6.0.0**.

#### Rationale
* **Modern aesthetic out of the box:** dark mode styling, rounded corners, `CTkSlider`, `CTkSegmentedButton`, `CTkSwitch`.
* **Lightweight:** adds roughly 2 MB to the packaged executable.
* **MIT licensed:** unrestricted distribution.

#### Consequences
* **Negative — accessibility:** CTk widgets are drawn on a `Canvas` and expose no UI Automation tree. **The application is not usable with Narrator or other screen readers.** This is a real, permanent limitation of the framework choice, disclosed in [[CLI and UX Interface Specification]] §1.4. Reversing it would mean adopting a UIA-backed toolkit and rewriting the entire UI layer.
* **Negative — small widget catalogue:** no message box, toast, tooltip, or table widget ships with the library (see ADR-011).
* **Negative — rendering cost:** Canvas-drawn widgets are heavier per instance than native controls, which constrains how many setting cards can be realised at once. Mitigated by virtualised rendering (see [[Technical Design Document]] §6).

---

### ADR-003: Use a Worker Thread with a Result Queue for Win32 Enumeration

**Status:** Accepted — **supersedes the `root.after()`-from-worker pattern in v1.0.0**

#### Context
Enumerating all deep Windows power settings requires traversing subgroups via repeated `PowerEnumerate`, `PowerReadFriendlyName`, `PowerReadDescription`, and bounds calls — roughly 800 FFI calls. On the main GUI thread this stalls the window for hundreds of milliseconds.

The initial design had the worker thread call `root.after(0, callback)` directly to marshal results back. **That pattern is not thread-safe.** Tkinter's C layer assumes single-threaded access; calling into it from a non-main thread can raise `RuntimeError: main thread is not in main loop` or crash the interpreter with `Tcl_AsyncDelete: async handler deleted by the wrong thread`. The failure is timing-dependent, so it survives casual testing and appears in the field.

#### Decision
Run all Win32 enumeration and registry reads on a dedicated **background worker thread**. The worker communicates **only** through a `queue.Queue`. The main thread drains that queue from a self-rescheduling `after(50, drain)` poller. **No worker thread ever touches a Tk object or calls any Tk method, including `after`.**

```python
# Worker thread — pure data, no Tk.
def enumerate_worker(scheme_guid, out_queue, cancel_event):
    try:
        for subgroup in power_manager.iter_subgroups(scheme_guid):
            if cancel_event.is_set():
                return
            out_queue.put(("subgroup", subgroup))
        out_queue.put(("done", None))
    except Exception as exc:
        out_queue.put(("error", exc))


# Main thread — the only code that touches widgets.
def drain(self):
    try:
        while True:
            kind, payload = self.queue.get_nowait()
            self.handle(kind, payload)
    except queue.Empty:
        pass
    self.after(50, self.drain)
```

#### Rationale
* The only pattern the Tkinter maintainers endorse for cross-thread updates.
* Incremental delivery: subgroups render as they arrive rather than after the whole tree completes, so the app feels responsive even on slow machines.
* The `cancel_event` lets a scheme switch abandon an in-flight enumeration instead of racing it.

#### Consequences
* **Positive:** No thread-safety class of bug; progressive rendering.
* **Negative:** Up to 50 ms of latency between a result being produced and rendered. Imperceptible, and the poll interval is a single tunable constant.
* **Note:** `ctypes` releases the GIL for the duration of each foreign call, so the worker genuinely runs in parallel with the UI.

---

### ADR-004: Least-Privilege Execution with On-Demand Elevation

**Status:** Accepted — mechanism revised by ADR-008

#### Context
Reading power settings, creating custom schemes (`PowerDuplicateScheme`), switching profiles (`PowerSetActiveScheme`), and changing AC/DC values (`PowerWriteACValueIndex`) require only **Standard User** permissions. Windows applies a default ACL to power policy objects granting read, write, and change to Authenticated Users.

Changing Control Panel visibility writes to `HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerSettings`, which requires **Administrator**.

#### Decision
The application manifest requests **`asInvoker`**. It launches and runs as a Standard User. Elevation is requested per-operation, only for visibility changes and `PowerRestoreDefaultPowerSchemes`, using the mechanism in ADR-008.

#### Rationale
* The overwhelming majority of user actions need no elevation. Prompting at launch would be a UAC prompt merely to *read* power plans.
* A GUI running with Administrator rights for its whole session is a far larger attack surface than a short-lived privileged writer.

#### Consequences
* Two privilege contexts must be reasoned about and tested. CI runners are always elevated, so the non-elevated path requires manual verification ([[Build Packaging and Release]] §6).
* `ERROR_ACCESS_DENIED` is ambiguous — it means either "not elevated" or "blocked by Group Policy". Disambiguation via `PowerSettingAccessCheck` is specified in [[Error Handling and Logging]] §3.1.

---

### ADR-005: OS Registry as Single Source of Truth for Power Data

**Status:** Accepted — **amended**, scope narrowed

#### Context
We evaluated whether to store power settings, custom scheme metadata, or cached setting definitions in a local SQLite database or JSON configuration file.

The original decision — "no external database **or local config file**" — proved too broad. It forbade remembering window size or the last-selected scheme, and it sat awkwardly beside the preset export feature, which writes local files by design.

#### Decision
**The Windows Registry and the `PowrProf` subsystem are the single source of truth for all power data.** No power setting value, scheme definition, or setting metadata is ever cached to disk or read from anywhere else.

**Amendment:** a small UI-state file is permitted at `%LOCALAPPDATA%\WindowsPowerExplorer\ui-state.json`, restricted to window geometry, last-selected scheme GUID, last-selected category, and search history. It contains **no power data**, and deleting it must be harmless.

#### Rationale
* Power settings change from many sources — `powercfg`, Control Panel, OEM utilities, Group Policy, Windows Update. Any cache would drift and start reporting stale values as truth.
* Reading live is cheap enough (see the enumeration benchmark) that a cache buys nothing.
* Window geometry is not power data, and the strict reading produced a worse product for no architectural gain.

#### Consequences
* Every UI refresh re-reads from the OS. Correct by construction.
* The UI-state file must be treated as untrusted on read — corrupt or hostile content falls back to defaults, never crashes.
* Backups written by [[Recovery and Destructive Operations]] are exports, not caches: they are never read back automatically.

---

### ADR-006: Write Visibility Attributes Directly to the Registry

**Status:** Accepted

#### Context
The Control Panel Unhider is a core product pillar. The documented API is `PowerWriteSettingAttributes(SubGroupGuid, PowerSettingGuid, Attributes)`, and Microsoft documents exactly one attribute value: `POWER_ATTRIBUTE_HIDE = 1`.

Two problems emerged:

1. **Writing `0` does not reliably unhide.** The value `powercfg.cpl` actually honours to *show* a setting is `2` — undocumented by Microsoft, but consistently used by every working unhide utility and observable in the registry on any Windows install. Reports of `PowerWriteSettingAttributes` failing to persist the reveal are long-standing.
2. **`PowerReadSettingAttributes` ORs in the subgroup's attributes.** A visible setting inside a hidden subgroup still reads as hidden, so both levels must be cleared.

#### Decision
* **Read** visibility through `PowerReadSettingAttributes` — it correctly folds in subgroup inheritance.
* **Write** visibility with `winreg` directly to `HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerSettings\{subgroup}[\{setting}]\Attributes`, writing `2` to reveal and `1` to hide, applying to both the setting and its parent subgroup when revealing.
* All writes are batched and performed by the elevated helper (ADR-008).

#### Rationale
* The documented API path does not deliver the feature. Shipping a headline feature that silently does nothing is worse than depending on an undocumented but stable registry convention.
* This registry layout has been stable since Windows Vista and is what the Control Panel itself reads.

#### Consequences
* **Negative:** We depend on undocumented behaviour. Mitigated by reading through the supported API, so a future Windows change would degrade the write path rather than corrupting our view of state.
* **Negative:** Visibility is **global** — system-wide and all-users — which is not per-scheme as the original UI implied. This forced the unhide control out of the per-scheme setting card and into a dedicated Control Panel Visibility view ([[Design Specification]] §4).
* **Positive:** Direct registry access makes the prior-state backup in [[Recovery and Destructive Operations]] §5 straightforward and exact.
* Windows feature updates reset these attributes; the app detects and offers to re-apply.

---

### ADR-007: JSON-Only Export; No `powercfg.exe` Shell-Out

**Status:** Accepted

#### Context
The PRD promised export to `.pow` files. Investigation found that **`powrprof.dll` exports no export function.** `PowerImportPowerScheme` exists; there is no `PowerExportPowerScheme`. The `.pow` format is written only by `powercfg.exe /export`, and it is an undocumented binary format.

Producing `.pow` files would require spawning `powercfg.exe` — which conflicts with the Threat Model's position on shell execution and adds a subprocess surface to an app that otherwise has none.

#### Decision
* **Export** to our own documented JSON preset format, built entirely from supported API reads.
* **Import** supports both our JSON format *and* `.pow` files, since `PowerImportPowerScheme` is a supported API.
* **No `powercfg.exe` invocation anywhere in the product.**

#### Rationale
* Asymmetry is acceptable and even useful: we read the ecosystem's format, and we write one that is human-readable, diffable, reviewable before import, and shareable as text in a forum post.
* JSON lets us carry things `.pow` cannot: intended visibility state, the source template, a description, and provenance metadata.
* Keeps the process tree flat, preserving the "no subprocess execution" property that makes the threat model simple.

#### Consequences
* **Negative:** Our exports are not consumable by `powercfg /import` or by other tools. Documented plainly in the UI: the export button reads "Export as JSON preset".
* **Negative:** Users wanting a true `.pow` backup must use `powercfg /export` themselves. The export dialog links to that command.
* **Positive:** Presets are reviewable before import, which is what makes the import diff in [[Recovery and Destructive Operations]] §7 possible at all.

---

### ADR-008: Elevated Helper Process Rather Than Relaunching the App

**Status:** Accepted — refines ADR-004

#### Context
The original design relaunched the entire application elevated via `ShellExecuteW("runas", sys.executable, ...)` when a visibility toggle needed Administrator. Three problems:

1. **State loss.** The user's scroll position, search filter, and selected scheme vanish mid-interaction — for a toggle.
2. **It contradicts ADR-004.** After relaunching, the whole GUI runs as Administrator for the rest of the session, which is exactly the standing privilege ADR-004 exists to avoid.
3. **No result feedback.** `ShellExecuteW` returns no process handle, so the original process cannot tell success from a declined prompt.

#### Decision
The main GUI **always** runs as Standard User and is never relaunched elevated. Operations requiring Administrator are serialised to a JSON batch file and executed by a short-lived elevated child process:

```text
main.py --elevated-helper "<path-to-batch.json>"
```

Launched via `ShellExecuteExW` with the `runas` verb and `SEE_MASK_NOCLOSEPROCESS`, so the parent can wait on the handle and read the exit code. The helper applies the batch, writes a result file, and exits. The GUI reads the result and updates its state in place.

#### Rationale
* One UAC prompt per batch of changes rather than per toggle, and no state loss.
* The privileged code path is small, auditable, and lives for milliseconds.
* An exit code and result file give real feedback, so the UI can report per-item outcomes instead of guessing.

#### Consequences
* **Positive:** Least privilege genuinely holds; declined prompts are handled gracefully.
* **Negative:** A batch protocol and a second entry point to specify and test.
* **Security:** The helper is the sole privileged surface, so it is hardened accordingly ([[Threat Model and Security Checklist]] §2.2): it accepts only a path to a batch file we wrote, validates every GUID against the live system before writing, refuses any registry path outside the `PowerSettings` subtree, and never interpolates user strings into its command line.

---

### ADR-009: Read-Only Awareness of Windows 11 Power Mode Overlays

**Status:** Accepted

#### Context
Windows 11 (and Windows 10 1809+) layers a **power mode overlay** — *Best power efficiency*, *Balanced*, *Best performance* — on top of the active power scheme. The overlay modifies effective behaviour without changing the scheme, and it is what the Settings app and battery flyout expose.

A user who sets a custom High Performance plan while the overlay sits on *Best power efficiency* sees none of their expected behaviour. Without surfacing this, the app appears broken.

The relevant functions — `PowerGetEffectiveOverlayScheme`, `PowerGetActualOverlayScheme`, `PowerSetActiveOverlayScheme` — are exported by `powrprof.dll` but **entirely undocumented**.

#### Decision
**Read and display the active overlay. Never write it.** The overlay is shown in the status bar with a short explanation of its interaction with the active scheme. Users are directed to Windows Settings to change it.

All overlay code degrades gracefully: a missing export, unknown GUID, or nonzero return hides the indicator and logs at `WARNING`. It never produces an error dialog and never blocks startup.

#### Rationale
* Solves the actual user problem — confusion — with a read-only dependency on undocumented API.
* Writing would put an undocumented setter on the critical path of a core interaction; the read path can fail invisibly, a failed write cannot.
* Windows Settings already offers a good control for this. Duplicating it is not our value.

#### Consequences
* **Positive:** Eliminates a whole class of "my settings don't apply" confusion at low risk.
* **Negative:** Users must leave the app to change power mode. Acceptable — it is one click in Settings, and the status bar links there.
* Revisit if Microsoft documents the setter.

---

### ADR-010: Ship Both Onefile and Onedir Artifacts

**Status:** Accepted

#### Context
The PRD promises a portable single-file `.exe`. The Test Plan targeted sub-350 ms cold start. **These are mutually exclusive.** A PyInstaller onefile binary is a self-extracting archive that unpacks CPython, Tcl/Tk, and all modules to `%TEMP%` on every launch — 1.5–3 s before any code runs. Onedir avoids extraction and starts in 0.4–0.8 s, but is a folder, not a file.

#### Decision
Ship **both** per release: `WindowsPowerExplorer-{ver}-x64.exe` (onefile, portable) and `WindowsPowerExplorer-{ver}-x64.zip` (onedir, fast). Identical code, separate startup benchmarks.

#### Rationale
* The two audiences genuinely differ. A technician running this from a USB stick wants one file and does not care about 2 seconds. Someone using it regularly wants it to open now.
* The marginal cost is one extra build target and one extra artifact to test and sign.

#### Consequences
* Two artifacts to build, test, sign, and publish; the release checklist covers both.
* Benchmarks are stated per-artifact ([[Test Plan and Benchmark Targets]] §3).
* Download page must explain the choice in one sentence, or users will pick arbitrarily.

---

### ADR-011: Build Dialogs In-House on `CTkToplevel`

**Status:** Accepted

#### Context
Earlier drafts referenced `CTkMessageBox` and `CTkToast`. **Neither exists.** CustomTkinter 6.0.0 exports exactly one dialog: `CTkInputDialog`. `CTkMessagebox` is a separate third-party package.

Three options: adopt the third-party package, use `tkinter.messagebox`, or build our own.

#### Decision
Implement a small internal `ui/dialogs/` module on `CTkToplevel`: a `ConfirmDialog` (with optional typed-phrase confirmation), an `ElevationDialog`, and an inline status-bar toast rather than floating notifications.

#### Rationale
* **Our destructive dialogs need custom behaviour anyway.** Typed-phrase confirmation, an embedded "Export first" action, and scrollable lists of affected schemes ([[Recovery and Destructive Operations]] §3) are beyond any generic message box.
* **Keeps runtime dependencies at three.** Every dependency is code we ship, must pin, must bundle, and must audit.
* `tkinter.messagebox` renders a native Win32 dialog that clashes badly with the dark theme — though it is worth noting it is the *only* screen-reader-accessible option, which is why it remains the fallback for the startup error window when the CTk stack itself has failed.

#### Consequences
* **Negative:** We own modal focus, `Escape` handling, `grab_set`, window centring, and default-button focus. Roughly 200 lines, written once.
* **Positive:** Full control over theming, copy, and confirmation semantics.
* Toasts are rendered as transient status-bar text rather than floating windows — fewer moving parts and no focus-stealing.
* **Exception:** the startup error window uses `tkinter.messagebox`. When binding verification has failed, the CTk stack may itself be unusable — and it is the one dialog that must reach a screen-reader user.

---

### ADR-012: Two-Phase Load — Setting Catalog Separate from Scheme Values

**Status:** Accepted

#### Context
The v1.0.0 design re-enumerated everything on every scheme switch: names, descriptions, bounds, possible values, attributes, policy checks, and AC/DC values — roughly eight read families per setting, ~800 FFI calls for a typical machine.

Auditing the actual signatures ([[Win32 API Reference]] §10.4) showed that **six of the eight families take no scheme parameter at all.** Only `PowerRead{AC,DC}ValueIndex` genuinely vary per scheme. The design was repeating about 75% of its work to re-read data that cannot have changed.

#### Decision
Split enumeration into two phases.

**Phase 1 — Catalog.** Built once at startup on the worker thread. Holds the subgroup/setting tree, friendly names, descriptions, bounds, increments, units, possible values, visibility attributes, and policy-lock flags. Rebuilt only on `Ctrl+R` or after a visibility batch is applied.

**Phase 2 — Values.** Run per scheme selection. Reads only `PowerReadACValueIndex` / `PowerReadDCValueIndex`, plus default indices keyed by the scheme's personality and cached per `(personality, subgroup, setting)`.

```python
@dataclass(frozen=True)
class SettingCatalogEntry:
    """Scheme-invariant. Built once per session."""
    guid: str
    subgroup_guid: str
    friendly_name: str
    description: str
    control_type: ControlType
    min_value: int | None
    max_value: int | None
    value_increment: int | None
    value_units: str
    choices: tuple[SettingValueChoice, ...]
    is_hidden: bool
    is_policy_locked: bool
    is_degraded: bool


@dataclass
class SchemeValues:
    """Per-scheme. Re-read on every scheme selection."""
    scheme_guid: str
    personality_guid: str
    ac: dict[str, int | None]           # setting GUID -> value
    dc: dict[str, int | None]
    ac_default: dict[str, int | None]
    dc_default: dict[str, int | None]
```

#### Rationale
* Scheme switching drops from ~800 FFI calls to ~200, and to ~150 when the personality's defaults are already cached.
* **It makes scheme comparison nearly free.** Two `SchemeValues` against one shared catalog is a dictionary diff — the whole compare feature becomes a view over data we already hold, rather than a second enumeration pass.
* The catalog is immutable and hashable, which makes it safe to hand to the UI thread without copying and trivial to reason about across threads.

#### Consequences
* **Positive:** Faster switching; comparison and "modified from default" become cheap; benchmark targets gain real headroom.
* **Negative:** Two structures to keep coherent, and a stale-catalog hazard — settings can appear or disappear when hardware changes or a driver installs. Mitigated by rebuilding the catalog on `Ctrl+R`, after any visibility batch, and whenever a value read returns `ERROR_FILE_NOT_FOUND` for a catalogued setting.
* **This is not a cache in the ADR-005 sense.** It is session-scoped, never written to disk, and holds no configured values — only the OS's own description of what settings exist. Configured values are still read live on every scheme selection.

---

### ADR-013: `powercfg` Script as a Third Export Format

**Status:** Accepted — extends ADR-007

#### Context
ADR-007 established that no `.pow` export API exists, so we export JSON. That left a real gap: JSON presets are only readable by this application. A technician who wants to apply a configuration through existing tooling — a deployment script, an MDM package, a runbook — has no path.

#### Decision
Add a third export format: a **generated `powercfg` script** (`.ps1` or `.cmd`) containing the `powercfg /setacvalueindex` and `/setdcvalueindex` commands that reproduce the scheme.

```powershell
# Windows Power Explorer — generated 2026-08-16T18:24:01Z
# Scheme: "Esports Ultra"  (from High Performance)
# Review before running. Requires no elevation except where noted.

$src  = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"   # High Performance
$dest = (powercfg /duplicatescheme $src) -replace '.*GUID: ([a-f0-9-]+).*','$1'
powercfg /changename $dest "Esports Ultra" "Max GPU and CPU state"

# Power plan personality -> High Performance
powercfg /setacvalueindex $dest fea3413e-7e05-4911-9a71-700331f1c294 245d8541-3943-4422-b025-13a784f679b7 1

# Processor performance boost mode
powercfg /setacvalueindex $dest 54533251-82be-4824-96c1-47b60b740d00 be337238-0d82-4146-a960-4f3749d470c7 0
powercfg /setdcvalueindex $dest 54533251-82be-4824-96c1-47b60b740d00 be337238-0d82-4146-a960-4f3749d470c7 0

powercfg /setactive $dest
```

**We generate text. We never execute it.** No subprocess is spawned, so the threat model is unchanged.

#### Rationale
* Recovers `.pow`-equivalent portability without the shell-out ADR-007 rejected.
* **Better than `.pow` in most respects:** human-readable, reviewable before running, diffable in version control, pasteable into a forum answer, and consumable by any existing automation.
* Costs one serializer over data we already hold.

#### Consequences
* **Positive:** Closes ADR-007's usability gap; makes the app useful to sysadmins who will never install it on the target machines.
* **Negative:** A generated script is a file users will run elevated. It carries a header comment naming its origin and timestamp, includes only literal GUIDs and integers we validated, and never interpolates a user-supplied string outside the quoted `/changename` arguments. Names are sanitised for quotes and control characters at generation time.
* Export offers three formats — JSON (round-trips through this app), `powercfg` script (portable automation), and a read-only Markdown summary for documentation.

---

### ADR-014: Portable Mode via a Sentinel File

**Status:** Accepted

#### Context
The PRD promises a portable single-file executable, but ADR-005's amendment writes UI state to `%LOCALAPPDATA%` and [[Error Handling and Logging]] writes logs there. A tool run from a USB stick on someone else's machine should not leave files in that user's profile — and NFR-6 already promises it leaves behind only its log and state files.

#### Decision
If a file named `portable.txt` sits beside the executable, the app runs in **portable mode**: UI state, logs, and backups are written to a `data/` directory next to the binary instead of `%LOCALAPPDATA%`. Absent that file, behaviour is unchanged.

```python
def data_root() -> Path:
    exe_dir = Path(sys.executable).parent
    if (exe_dir / "portable.txt").exists() and os.access(exe_dir, os.W_OK):
        return exe_dir / "data"
    return Path(os.environ["LOCALAPPDATA"]) / "WindowsPowerExplorer"
```

#### Rationale
* A sentinel file needs no installer, no registry entry, and no command-line flag to remember. Users create an empty file; that is the whole interface.
* The writability check matters: a USB stick can be read-only, and a portable app that crashes on startup because it cannot write a log is worse than one that quietly falls back.

#### Consequences
* **Positive:** Genuinely portable; leaves no trace on a borrowed machine.
* **Negative:** Two path roots to test. The elevated helper must be told the root explicitly rather than recomputing it — under elevation `%LOCALAPPDATA%` may resolve to a different profile, so the batch file carries the resolved path.
* **Security:** the helper still validates that the path it is given is inside either the portable `data/` directory or the invoking user's `%LOCALAPPDATA%`, and refuses anything else.
* Portable mode is the default in the onefile artifact's documentation, since that is the artifact people copy to removable media.
