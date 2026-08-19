"""Scheme Export Modal Dialog (ADR-007, ADR-011, REQ-4.1, Issue #23).

Supports exporting the selected power scheme in three distinct formats:
1. JSON Preset (.json)
2. powercfg CLI script commands (.bat / .cmd)
3. Markdown documentation table (.md)
"""

import json
import tkinter.filedialog
from typing import Any

import customtkinter as ctk

from core.controller import AppController
from core.models import PowerScheme
from ui.dialogs.base import BaseDialog
from ui.theme import (
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_SURFACE_CARD,
    COLOR_SURFACE_HOVER,
    COLOR_SURFACE_SECONDARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_SUBTITLE,
)


class ExportDialog(BaseDialog):
    """Modal dialog for exporting power schemes to JSON, powercfg scripts, or Markdown."""

    def __init__(
        self,
        parent: Any,
        controller: AppController,
        scheme: PowerScheme | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, title="Export Power Scheme", width=620, height=480, **kwargs)
        self.controller = controller
        self.scheme = scheme or self.controller.state.selected_scheme or self.controller.state.active_scheme
        self.current_format = "JSON Preset"
        self._build_ui()
        self._update_preview()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        scheme_name = self.scheme.friendly_name if self.scheme else "Current Scheme"
        scheme_guid = self.scheme.guid if self.scheme else ""

        # 1. Header
        header_box = ctk.CTkFrame(self, fg_color="transparent")
        header_box.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="ew")

        ctk.CTkLabel(
            header_box,
            text=f"Export: {scheme_name}",
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_box,
            text=f"GUID: {scheme_guid}",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        ).pack(anchor="w")

        # 2. Format Segmented Switch
        format_box = ctk.CTkFrame(self, fg_color="transparent")
        format_box.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(
            format_box,
            text="Export Format:",
            font=FONT_BODY_BOLD,
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 10))

        self.format_seg = ctk.CTkSegmentedButton(
            format_box,
            values=["JSON Preset", "powercfg Script", "Markdown Summary"],
            command=self._on_format_changed,
            font=FONT_BODY,
        )
        self.format_seg.set("JSON Preset")
        self.format_seg.pack(side="left")

        # 3. Preview Textbox
        self.preview_box = ctk.CTkTextbox(
            self,
            font=("Consolas", 10),
            fg_color=COLOR_SURFACE_CARD,
            border_color=COLOR_BORDER,
            border_width=1,
            wrap="none",
        )
        self.preview_box.grid(row=2, column=0, padx=20, pady=4, sticky="nsew")

        # 4. Footer Action Buttons
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.grid(row=3, column=0, padx=20, pady=(8, 16), sticky="ew")

        self.close_btn = ctk.CTkButton(
            btn_box,
            text="Close",
            font=FONT_BODY,
            fg_color=COLOR_SURFACE_SECONDARY,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            command=self.destroy,
            width=90,
        )
        self.close_btn.pack(side="right", padx=(8, 0))

        self.save_btn = ctk.CTkButton(
            btn_box,
            text="Save to File...",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            command=self._save_to_file,
            width=110,
        )
        self.save_btn.pack(side="right", padx=(8, 0))

        self.copy_btn = ctk.CTkButton(
            btn_box,
            text="Copy to Clipboard",
            font=FONT_BODY,
            fg_color=COLOR_SURFACE_SECONDARY,
            text_color=COLOR_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            command=self._copy_clipboard,
            width=130,
        )
        self.copy_btn.pack(side="right")

        # Initial focus on safe Close button
        self.close_btn.focus_set()

    def _on_format_changed(self, choice: str) -> None:
        self.current_format = choice
        self._update_preview()

    def _generate_export_text(self) -> str:
        if not self.scheme:
            return ""

        s_guid = self.scheme.guid
        s_name = self.scheme.friendly_name
        s_desc = self.scheme.description
        values = self.controller.state.values
        catalog = self.controller.state.catalog

        if self.current_format == "JSON Preset":
            settings_payload = []
            if catalog and values:
                for sub in catalog.subgroups:
                    for s in sub.settings:
                        key = s.guid.lower()
                        ac_val = values.ac.get(key)
                        dc_val = values.dc.get(key)
                        if ac_val is not None or dc_val is not None:
                            settings_payload.append({
                                "subgroup_guid": sub.guid,
                                "setting_guid": s.guid,
                                "friendly_name": s.friendly_name,
                                "ac_value": ac_val,
                                "dc_value": dc_val,
                            })

            data = {
                "$schema": "https://github.com/apollo-jhn/windows-power-explorer/schema/power_preset.schema.json",
                "version": 2,
                "scheme": {
                    "guid": s_guid,
                    "friendly_name": s_name,
                    "description": s_desc,
                    "is_base_default": self.scheme.is_base_default,
                },
                "settings": settings_payload,
            }
            return json.dumps(data, indent=2)

        elif self.current_format == "powercfg Script":
            lines = [
                "@echo off",
                f":: Windows Power Explorer Export for '{s_name}'",
                f":: Target Scheme GUID: {s_guid}",
                "",
                f"powercfg -changename {s_guid} \"{s_name}\" \"{s_desc}\"",
                "",
            ]
            if catalog and values:
                for sub in catalog.subgroups:
                    for s in sub.settings:
                        key = s.guid.lower()
                        ac = values.ac.get(key)
                        dc = values.dc.get(key)
                        if ac is not None:
                            lines.append(f"powercfg -setacvalueindex {s_guid} {sub.guid} {s.guid} {ac}")
                        if dc is not None and self.controller.state.has_battery:
                            lines.append(f"powercfg -setdcvalueindex {s_guid} {sub.guid} {s.guid} {dc}")
            lines.append("")
            lines.append("echo Power settings applied successfully.")
            return "\n".join(lines)

        else:  # Markdown Summary
            lines = [
                f"# Power Scheme: {s_name}",
                f"- **GUID:** `{s_guid}`",
                f"- **Description:** {s_desc}",
                f"- **Type:** {'Built-in Windows Scheme' if self.scheme.is_base_default else 'Custom Scheme'}",
                "",
                "| Subgroup | Setting | GUID | AC Value | DC Value |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
            if catalog and values:
                for sub in catalog.subgroups:
                    for s in sub.settings:
                        key = s.guid.lower()
                        ac = values.ac.get(key, "-")
                        dc = values.dc.get(key, "-")
                        lines.append(f"| {sub.friendly_name} | {s.friendly_name} | `{s.guid}` | {ac} | {dc} |")
            return "\n".join(lines)

    def _update_preview(self) -> None:
        text = self._generate_export_text()
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("1.0", text)
        self.preview_box.configure(state="disabled")

    def _copy_clipboard(self) -> None:
        text = self._generate_export_text()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.copy_btn.configure(text="✓ Copied!")
        self.after(2000, lambda: self.copy_btn.configure(text="Copy to Clipboard"))

    def _save_to_file(self) -> None:
        text = self._generate_export_text()
        ext = ".json" if self.current_format == "JSON Preset" else (".bat" if self.current_format == "powercfg Script" else ".md")
        file_types = [("JSON Files", "*.json")] if ext == ".json" else ([("Batch Scripts", "*.bat")] if ext == ".bat" else [("Markdown Files", "*.md")])

        path = tkinter.filedialog.asksaveasfilename(
            parent=self,
            title="Save Export File",
            defaultextension=ext,
            filetypes=file_types,
            initialfile=f"power_scheme_{self.scheme.friendly_name.lower().replace(' ', '_')}{ext}" if self.scheme else f"export{ext}",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.save_btn.configure(text="✓ Saved!")
                self.after(2000, lambda: self.save_btn.configure(text="Save to File..."))
            except Exception:
                pass
