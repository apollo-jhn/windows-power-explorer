# Build, Packaging and Release

* **Document Version:** 1.0.0
* **Target Stack:** Python 3.10+, `PyInstaller` 6.13+
* **Related Documents:** [[Index]], [[Test Plan and Benchmark Targets]], [[Threat Model and Security Checklist]], [[Architecture Decision Records]]

---

## 1. Distribution Matrix

We ship **two artifacts per release** (ADR-010). They differ only in packaging — same code, same version.

| Artifact | Form | Cold start | Use case |
| :--- | :--- | :--- | :--- |
| `WindowsPowerExplorer-{ver}-x64.exe` | PyInstaller **onefile** | 1.5 – 3 s | Portable. Copy to a USB stick, run on any machine, leave nothing behind. |
| `WindowsPowerExplorer-{ver}-x64.zip` | PyInstaller **onedir**, zipped | 0.4 – 0.8 s | Installed use. Extract once, launch fast every time. |

The onefile artifact ships alongside an empty **`portable.txt`** in its release notes as a one-line instruction: drop that file next to the `.exe` and the app keeps its state, logs, and backups beside itself instead of in `%LOCALAPPDATA%` (ADR-014). This is what makes "leave nothing behind" literally true rather than approximately true.

> [!NOTE]
> **Why onefile is slow.** A onefile executable is a self-extracting archive: every launch
> unpacks the Python runtime, Tcl/Tk, and all modules into a fresh `%TEMP%\_MEIxxxxxx`
> directory, then deletes it on exit. That extraction dominates startup and cannot be
> optimised away. It is the price of the single-file portability the PRD promises, which
> is why we ship onedir alongside it rather than choosing between them.

The two artifacts are **behaviourally identical** and both must pass the full test suite. The startup benchmarks in [[Test Plan and Benchmark Targets]] §3 are stated per-artifact.

---

## 2. Architecture Support

| Target | Status | Build method |
| :--- | :--- | :--- |
| **Windows x64** | Fully supported, released | PyInstaller on an x64 build host |
| **Windows ARM64** | Supported via x64 emulation | The x64 artifact runs under Windows-on-ARM emulation |
| **Windows ARM64 native** | Best-effort, not released | Requires building **on** an ARM64 host |

> [!WARNING]
> **PyInstaller cannot cross-compile for Windows ARM64.** Native ARM64 bootloaders
> arrived in PyInstaller 6.13.0, but they must be built on an actual ARM64 Windows
> machine — `--target-arch=arm64` on an x64 host silently produces an x64 binary.
> GitHub Actions offers no hosted Windows ARM64 runner.
>
> We therefore ship **x64 only**, and Windows-on-ARM users run it under emulation.
> Emulation is fine for this app: it is I/O- and registry-bound, not compute-bound,
> and `powrprof.dll` calls are thunked transparently. A native ARM64 build may be
> produced manually if a maintainer has the hardware, but it is not a release gate.

This supersedes the unqualified "ARM64 Supported" claim in earlier revisions of the Test Plan.

---

## 3. Dependency Policy

`requirements.txt` is fully pinned, including transitive dependencies:

```text
customtkinter==6.0.0
darkdetect==0.8.0
packaging==26.3
```

`requirements-dev.txt`:

```text
-r requirements.txt
pyinstaller==6.22.0
pytest==8.3.4
pytest-cov==6.0.0
jsonschema==4.23.0
```

**Rules:**

* Runtime dependencies stay at **three**. Every addition needs an ADR.
* `jsonschema` is **dev/test only** — the shipped app validates imported presets with hand-written checks (see [[Data Flow and Configuration Schema]] §2.2) so no fourth runtime dependency is bundled. The formal schema file is the contract our tests verify against.
* Dialogs and toasts are built in-house on `CTkToplevel` rather than pulling `CTkMessagebox` (ADR-011). CustomTkinter 6.0.0 ships only `CTkInputDialog`.
* **No networking libraries may appear anywhere in the dependency tree.** CI asserts this — see §6.

---

## 4. PyInstaller Specification

```python
# build/power_explorer.spec
# Shared analysis; two build targets produced from it.

block_cipher = None

a = Analysis(
    ["../main.py"],
    pathex=["../"],
    binaries=[],
    datas=[
        ("../assets", "assets"),
        ("../data", "data"),        # essentials, reboot_required, doc_links (REQ-10)
        ("../schema", "schema"),
    ],
    hiddenimports=[],
    excludes=[
        # Never bundled — enforced by the threat model.
        "urllib3", "requests", "http", "socket", "ssl", "email",
        "ftplib", "smtplib", "xmlrpc",
        # Dead weight from the stdlib.
        "unittest", "pydoc", "doctest", "test", "sqlite3",
        "pdb", "distutils", "lib2to3", "multiprocessing",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
```

**Onefile target:**

```python
exe_onefile = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="WindowsPowerExplorer",
    console=False,               # see §4.1
    icon="../assets/icon.ico",
    version="../build/version_info.txt",
    upx=False,                   # see §4.2
    manifest="../build/app.manifest",
)
```

**Onedir target:** same `EXE(...)` without the binary payload, followed by a `COLLECT(...)`.

### 4.1 The Console Problem

`console=False` produces a windowed app with **no stdout or stderr**. The CLI in `main.py` then has nowhere to print, and `list-schemes --json` returns nothing when run from PowerShell.

**Resolution:** ship a windowed executable and reattach to the parent console when a CLI subcommand is present.

```python
def attach_console() -> None:
    """Reattach to the launching console so CLI output is visible."""
    if ctypes.windll.kernel32.AttachConsole(-1):   # ATTACH_PARENT_PROCESS
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
```

Call this before argument dispatch whenever `sys.argv` carries a subcommand. When `AttachConsole` fails (launched from Explorer with CLI args), fall back to writing results to a temp file and reporting its path — never crash on a missing stream.

### 4.1b Bundled Data and `sys._MEIPASS`

Read-only bundled files (`assets/`, `data/`, `schema/`) are extracted to `sys._MEIPASS` when frozen and sit beside the source tree when not. All three must resolve through one helper — hardcoding `Path(__file__).parent` works in development and fails in the onefile artifact:

```python
def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)
```

> [!IMPORTANT]
> **`sys._MEIPASS` is read-only and is deleted when the process exits.** It must never be
> confused with the portable-mode `data/` directory from ADR-014, which sits beside the
> executable and is written to. They share a name and nothing else. `core/paths.py` owns
> the writable root; `resource_path` owns the bundled one, and neither may call the other.

The portable sentinel is probed at `Path(sys.executable).parent`, which under onefile is the **real** location of the `.exe`, not the extraction directory — `sys.executable` is correct here and `__file__` is not.

### 4.2 UPX Is Disabled

UPX compression shaves a few MB but is a strong heuristic signal for antivirus engines. An unsigned, UPX-packed executable that writes to `HKLM` power keys is close to a worst case for false positives. Size is not worth the support burden.

### 4.3 Application Manifest

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges>
        <!-- Standard User. Elevation is per-operation via the helper (ADR-008). -->
        <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>

  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <!-- Windows 10 and 11 -->
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
    </application>
  </compatibility>

  <asmv3:application xmlns:asmv3="urn:schemas-microsoft-com:asm.v3">
    <asmv3:windowsSettings>
      <!-- Required: Tk renders blurry on scaled displays without this. -->
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">permonitorv2</dpiAwareness>
    </asmv3:windowsSettings>
  </asmv3:application>
</assembly>
```

`asInvoker` is deliberate: the manifest must **not** request `requireAdministrator`, or the least-privilege model in ADR-004 collapses and every user gets a UAC prompt merely to read their power plans.

---

## 5. Versioning and Release

**Semantic versioning**, single source of truth in `core/__version__.py`, propagated to the `version_info.txt` resource block by the build script.

| Change | Bump |
| :--- | :--- |
| Preset JSON schema gains a required field | **Major** |
| New CLI subcommand, new UI feature | **Minor** |
| Bug fix, copy change, dependency patch | **Patch** |

The preset `version` field is independent of the app version and changes only when the preset format itself changes. Importers accept any preset whose major version they recognise.

### 5.1 Release Checklist

1. All tests green on Windows 10 19045 and Windows 11 26200.
2. Version bumped in `core/__version__.py`; `CHANGELOG.md` updated.
3. Both artifacts built from a clean checkout.
4. Both artifacts smoke-tested on a machine with **no Python installed**.
5. Artifacts signed (§5.2), signatures verified with `signtool verify /pa`.
6. `SHA256SUMS.txt` generated and published alongside.
7. Tag `v{version}`, GitHub release with both artifacts and the checksum file.

### 5.2 Code Signing

Unsigned binaries trigger SmartScreen, which for a tool that edits system power policy reads exactly like malware to a cautious user.

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /a WindowsPowerExplorer-1.0.0-x64.exe
```

Timestamping (`/tr`) is mandatory — without it, signatures expire with the certificate and every previously shipped release starts warning. Signing is a **release gate for tagged releases only**; CI builds of `main` are unsigned and marked as such.

The signing certificate never enters the repository or CI secrets in exportable form. Where an EV certificate on a hardware token is used, tagged releases are signed manually by a maintainer.

---

## 6. Continuous Integration

`windows-latest` runners only. Linux and macOS runners cannot load `powrprof.dll` and would produce meaningless results.

```yaml
name: build
on: [push, pull_request]

jobs:
  test:
    runs-on: windows-latest
    strategy:
      matrix:
        python: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}" }
      - run: pip install -r requirements-dev.txt
      - run: pytest -m "not gui" --cov=core --cov-fail-under=85
      - run: python build/assert_no_network_imports.py
```

**Constraints CI must respect:**

* **GUI tests do not run in CI.** GitHub Actions runners have no interactive desktop session; `CTk()` fails to obtain a display. GUI tests are marked `@pytest.mark.gui` and excluded here, run manually before release. See [[Test Plan and Benchmark Targets]] §2.3.
* **Elevation tests do not run in CI.** Runners are already elevated, which makes the non-elevated path untestable there. `PowerWriteSettingAttributes` paths are mocked in CI and verified manually.
* **Integration tests are read-only in CI.** Any test that mutates registry state must be marked `@pytest.mark.mutating` and is excluded from CI runs.
* **Coverage gate is 85%** on `core/`. UI modules are excluded from the gate.

### 6.1 The No-Network Assertion

The Threat Model's zero-network guarantee is enforced mechanically, not by review:

```python
# build/assert_no_network_imports.py
import ast, pathlib, sys

FORBIDDEN = {
    "socket", "ssl", "http", "urllib", "urllib3", "requests",
    "ftplib", "smtplib", "telnetlib", "xmlrpc", "asyncio",
}

failures = []
for path in pathlib.Path("core").rglob("*.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name.split(".")[0] in FORBIDDEN:
                failures.append(f"{path}:{node.lineno}: forbidden import {name!r}")

if failures:
    print("\n".join(failures), file=sys.stderr)
    sys.exit(1)
print("No network imports found.")
```

A matching post-build check greps the frozen artifact's module table for the same names, catching anything a dependency drags in.

---

## 7. Reproducibility

* `SOURCE_DATE_EPOCH` is set from the git commit timestamp so `.pyc` files are deterministic.
* All dependencies pinned to exact versions, including build tooling.
* `pip install --require-hashes` against a generated `requirements.lock`.
* Build host Python version recorded in the release notes.

Byte-identical reproducibility is **not** claimed — PyInstaller embeds paths and timestamps that vary. The goal is that two builds from the same commit behave identically and contain the same module set, which §6.1's post-build check verifies.
