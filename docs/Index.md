# Windows Power Explorer — Documentation Vault

Welcome to the **Windows Power Explorer** Obsidian vault! This documentation outlines the product specifications, technical architecture, design decisions, data flow, configuration schemas, CLI commands, test strategy, threat model, and Win32 C-FFI API mappings for building a modern, lightweight replacement for *PowerSettingsExplorer*.

---

## 🗺️ Map of Content (MOC)

### Product & Architecture
* 📄 **[[Product Requirements Document]]** — Product Goals, Personas, In/Out Scope, Functional Specifications.
* ⚙️ **[[Technical Design Document]]** — Technical Architecture & RFC (Python 3.10+, `ctypes` Win32 C-FFI, `customtkinter` layout, Threading Engine).
* 🏛️ **[[Architecture Decision Records]]** — ADRs 001–011 (Tech Stack, GUI, Threading, Elevation, Registry model, Visibility writes, Export format, Overlays, Distribution, Dialogs).

### Interface & Data
* 🎨 **[[Design Specification]]** — Visual Interface Specification, UI Component Hierarchy, and Feature Blueprint.
* 🖥️ **[[CLI and UX Interface Specification]]** — Dark Theme Palette, Component Hierarchy, Shortcuts, and Headless CLI Commands.
* 🔄 **[[Data Flow and Configuration Schema]]** — System Data Flows, Sequence Diagrams, Python Data Models, JSON Preset Schemas, and Registry Structures.

### Implementation Reference
* 🔌 **[[Win32 API Reference]]** — **Authoritative** C-FFI binding reference: signatures, `argtypes`/`restype`, buffer protocols, memory ownership, error codes, well-known GUIDs.
* 🧯 **[[Error Handling and Logging]]** — Exception hierarchy, Win32 code → user message map, enumeration resilience, log configuration, crash handling.
* ♻️ **[[Recovery and Destructive Operations]]** — Destructive operation register, backup requirements, confirmation flows, import safety.

### Quality & Delivery
* 🧪 **[[Test Plan and Benchmark Targets]]** — Unit, Integration, GUI, and CLI Test Automation Strategy, Benchmarks, and OS Matrix.
* 🛡️ **[[Threat Model and Security Checklist]]** — STRIDE Analysis, Privilege Isolation, Input Sanitization, and C-FFI Hardening.
* 📦 **[[Build Packaging and Release]]** — PyInstaller specification, distribution artifacts, architecture support, signing, CI pipeline.

---

## ⚡ Project Overview

* **Application Name:** Windows Power Explorer
* **Target Operating System:** Windows 10 (19041+) & Windows 11 (x64; ARM64 via emulation)
* **Language & Runtime:** Python 3.10+
* **GUI Framework:** `customtkinter` 6.0.0 (Dark-themed modern GUI engine)
* **Win32 Interop:** Python `ctypes` (direct calls to `PowrProf.dll`, `kernel32.dll`, `shell32.dll`) plus `winreg` for visibility attributes
* **CLI Engine:** Python `argparse` (Headless scripting & automation support)
* **Executable Build:** `PyInstaller` (portable single-file `.exe` **and** fast-start onedir ZIP)

---

## 📐 Document Precedence

Where documents disagree on a technical detail, resolve in this order:

1. **[[Win32 API Reference]]** — binding signatures, buffer protocols, error semantics, GUIDs
2. **[[Architecture Decision Records]]** — architectural choices and their rationale
3. **[[Product Requirements Document]]** — feature scope and behaviour
4. Everything else

---

## ⚠️ Implementation Landmines

Five findings that contradict the obvious approach. Each is specified in full in [[Win32 API Reference]].

1. **Visibility lives in a different registry tree than scheme values, and it is global.** `Attributes` sits under `…\Control\Power\PowerSettings\`, not under `PowerSchemes\`. Unhiding a setting reveals it for every power plan and every user on the machine.
2. **The working "unhide" value is `2`, and it is undocumented.** Microsoft documents only `POWER_ATTRIBUTE_HIDE = 1`. Writing `0` does not reliably reveal a setting (ADR-006).
3. **`PowerSetActiveScheme` switches the machine's active plan.** Calling it to "refresh" after editing a non-active scheme silently moves the user onto that plan. Only refresh when the edited scheme *is* the active one.
4. **There is no export API.** `powrprof.dll` exports an importer but no exporter (ADR-007).
5. **Windows 11's Power Mode overlay silently overrides the active scheme.** Without surfacing it, users report that their settings "don't apply" (ADR-009).

---

## 📸 Interface Concept

![[ui_mockup.jpg]]
