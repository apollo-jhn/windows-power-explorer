"""Setting Card Widget with AC/DC controls, badges, and metadata (Issue #20, #26, #28).

Renders a single power setting with:
- Friendly name & description (with GUID fallback for unknown settings)
- Independent AC and DC controls with inferred widget types (REQ-2.4)
- Modified badge (●) and per-setting Reset button (REQ-9.2, REQ-9.3)
- Link AC/DC toggle (🔗) (REQ-11.3)
- Bulk edit across custom schemes (REQ-11.4)
- Policy-locked state (🔒 disabled + explanation) (REQ-2.5)
- Hazard warnings & reboot-required indicators (REQ-10.6)
- Right-click / context menu: Copy GUID, Copy powercfg, Pin/unpin favorite, Copy doc link
- Battery-less machine DC row omission (REQ-2.6)
"""

import logging
import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk

from core.controller import AppController
from core.models import ControlType, SettingCatalogEntry
from ui.theme import (
    COLOR_BORDER,
    COLOR_MODIFIED_BADGE,
    COLOR_MODIFIED_BG,
    COLOR_PRIMARY,
    COLOR_SURFACE_CARD,
    COLOR_SURFACE_HOVER,
    COLOR_SURFACE_SECONDARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    FONT_BADGE,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_SUBTITLE,
)

logger = logging.getLogger(__name__)


class SettingCardWidget(ctk.CTkFrame):
    """Card widget rendering a single power setting."""

    def __init__(
        self,
        master: Any,
        setting: SettingCatalogEntry,
        controller: AppController,
        doc_url: str | None = None,
        reboot_required: bool = False,
        on_refresh: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLOR_SURFACE_CARD,
            border_color=COLOR_BORDER,
            border_width=1,
            corner_radius=8,
            **kwargs,
        )
        self.setting = setting
        self.controller = controller
        self.doc_url = doc_url
        self.reboot_required = reboot_required
        self.on_refresh = on_refresh

        self.is_linked = False
        self._updating_widgets = False

        # Current values
        s_key = self.setting.guid.lower()
        self.ac_val = (
            self.controller.state.values.ac.get(s_key)
            if self.controller.state.values
            else None
        )
        self.dc_val = (
            self.controller.state.values.dc.get(s_key)
            if self.controller.state.values
            else None
        )

        self._build_ui()
        self._bind_context_menu()

    def _build_ui(self) -> None:
        """Construct setting card layout."""
        self.grid_columnconfigure(0, weight=1)

        # 1. Header Frame (Title + Badges + Reset)
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        header_frame.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")

        # Name with fallback
        display_name = self.setting.friendly_name or f"Unknown setting ({self.setting.guid[:8]}...)"
        self.title_label = ctk.CTkLabel(
            title_box,
            text=display_name,
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self.title_label.pack(side="left", padx=(0, 8))

        # Badges frame
        self.badges_frame = ctk.CTkFrame(title_box, fg_color="transparent")
        self.badges_frame.pack(side="left")

        # Modified badge (REQ-9.2)
        is_mod = self.controller.state.is_setting_modified(self.setting.guid)
        if is_mod:
            mod_badge = ctk.CTkLabel(
                self.badges_frame,
                text="● Modified",
                font=FONT_BADGE,
                text_color=COLOR_MODIFIED_BADGE,
                fg_color=COLOR_MODIFIED_BG,
                corner_radius=4,
                padx=6,
                pady=2,
            )
            mod_badge.pack(side="left", padx=(0, 6))

        # Policy locked badge (REQ-2.5)
        if self.setting.is_policy_locked:
            lock_badge = ctk.CTkLabel(
                self.badges_frame,
                text="🔒 Managed",
                font=FONT_BADGE,
                text_color=COLOR_WARNING,
                corner_radius=4,
                padx=6,
                pady=2,
            )
            lock_badge.pack(side="left", padx=(0, 6))

        # Reboot required indicator (REQ-10.6)
        if self.reboot_required:
            reboot_badge = ctk.CTkLabel(
                self.badges_frame,
                text="↻ Reboot required",
                font=FONT_BADGE,
                text_color=COLOR_WARNING,
                corner_radius=4,
                padx=6,
                pady=2,
            )
            reboot_badge.pack(side="left", padx=(0, 6))

        # Favorite star indicator
        if self.controller.state.is_favorite(self.setting.subgroup_guid, self.setting.guid):
            fav_badge = ctk.CTkLabel(
                self.badges_frame,
                text="★",
                font=FONT_SUBTITLE,
                text_color=COLOR_PRIMARY,
            )
            fav_badge.pack(side="left", padx=(0, 6))

        # Action buttons on header right (Reset, Link, Menu)
        actions_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=1, sticky="e")

        # Reset button (REQ-9.3)
        self.reset_btn = ctk.CTkButton(
            actions_frame,
            text="Reset",
            width=54,
            height=24,
            font=FONT_SMALL,
            fg_color=COLOR_SURFACE_SECONDARY,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            command=self._on_reset,
            state="normal" if is_mod and not self.setting.is_policy_locked else "disabled",
        )
        self.reset_btn.pack(side="left", padx=(0, 6))

        # Link AC/DC toggle (REQ-11.3)
        if self.controller.state.has_battery:
            self.link_btn = ctk.CTkButton(
                actions_frame,
                text="🔗 Link",
                width=56,
                height=24,
                font=FONT_SMALL,
                fg_color=COLOR_PRIMARY if self.is_linked else COLOR_SURFACE_SECONDARY,
                text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                command=self._toggle_link,
                state="disabled" if self.setting.is_policy_locked else "normal",
            )
            self.link_btn.pack(side="left", padx=(0, 6))

        # More actions / context button
        self.more_btn = ctk.CTkButton(
            actions_frame,
            text="•••",
            width=32,
            height=24,
            font=FONT_BODY_BOLD,
            fg_color=COLOR_SURFACE_SECONDARY,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            command=self._show_context_menu_from_button,
        )
        self.more_btn.pack(side="left")

        # 2. Description & GUID
        desc_text = self.setting.description or f"GUID: {self.setting.guid}"
        self.desc_label = ctk.CTkLabel(
            self,
            text=desc_text,
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
            wraplength=700,
            justify="left",
        )
        self.desc_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        # Policy locked warning explanation
        if self.setting.is_policy_locked:
            policy_desc = ctk.CTkLabel(
                self,
                text="Managed by your organization. Setting cannot be modified on this machine.",
                font=FONT_SMALL,
                text_color=COLOR_WARNING,
                anchor="w",
            )
            policy_desc.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 6))

        # 3. Controls Frame
        controls_container = ctk.CTkFrame(self, fg_color="transparent")
        controls_container.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 12))
        controls_container.grid_columnconfigure(1, weight=1)

        # AC Row
        self.ac_widget = self._build_control_row(
            controls_container,
            row=0,
            label_text="AC (Plugged In):",
            current_value=self.ac_val,
            rail="ac",
        )

        # DC Row (Omitted if no battery per REQ-2.6)
        if self.controller.state.has_battery:
            self.dc_widget = self._build_control_row(
                controls_container,
                row=1,
                label_text="DC (On Battery):",
                current_value=self.dc_val,
                rail="dc",
            )
        else:
            self.dc_widget = None

    def _build_control_row(
        self,
        container: ctk.CTkFrame,
        row: int,
        label_text: str,
        current_value: int | None,
        rail: str,
    ) -> Any:
        """Create an individual AC or DC control row based on inferred control type."""
        lbl = ctk.CTkLabel(
            container,
            text=label_text,
            font=FONT_BODY,
            text_color=COLOR_TEXT_PRIMARY,
            width=110,
            anchor="w",
        )
        lbl.grid(row=row, column=0, sticky="w", pady=4)

        row_frame = ctk.CTkFrame(container, fg_color="transparent")
        row_frame.grid(row=row, column=1, sticky="ew", pady=4)
        row_frame.grid_columnconfigure(0, weight=1)

        disabled = self.setting.is_policy_locked

        if self.setting.control_type == ControlType.ENUM:
            choices = self.setting.choices
            choice_map = {c.value_index: c.friendly_name for c in choices}
            name_to_val = {c.friendly_name: c.value_index for c in choices}

            display_val = choice_map.get(current_value, str(current_value) if current_value is not None else "Unknown")
            options = [c.friendly_name for c in choices] or [display_val]

            def on_enum_change(choice_name: str) -> None:
                if self._updating_widgets:
                    return
                val = name_to_val.get(choice_name, current_value)
                if val is not None:
                    self._on_user_value_change(val, rail)

            menu = ctk.CTkOptionMenu(
                row_frame,
                values=options,
                command=on_enum_change,
                width=240,
                height=26,
                font=FONT_BODY,
                state="disabled" if disabled else "normal",
            )
            menu.set(display_val)
            menu.grid(row=0, column=0, sticky="w")
            return menu

        elif self.setting.control_type == ControlType.TOGGLE:
            val_int = 1 if current_value == 1 else 0
            switch_var = tk.IntVar(value=val_int)

            def on_toggle() -> None:
                if self._updating_widgets:
                    return
                new_v = switch_var.get()
                self._on_user_value_change(new_v, rail)

            switch = ctk.CTkSwitch(
                row_frame,
                text="Enabled" if val_int == 1 else "Disabled",
                variable=switch_var,
                command=on_toggle,
                font=FONT_BODY,
                state="disabled" if disabled else "normal",
            )

            def update_text():
                switch.configure(text="Enabled" if switch_var.get() == 1 else "Disabled")

            switch_var.trace_add("write", lambda *_: update_text())
            switch.grid(row=0, column=0, sticky="w")
            return switch

        elif self.setting.control_type == ControlType.RANGE:
            min_v = self.setting.min_value if self.setting.min_value is not None else 0
            max_v = self.setting.max_value if self.setting.max_value is not None else 100
            inc = self.setting.value_increment or 1
            cur_v = current_value if current_value is not None else min_v

            units = f" {self.setting.value_units}" if self.setting.value_units else ""
            val_label = ctk.CTkLabel(
                row_frame,
                text=f"{cur_v}{units}",
                font=FONT_BODY_BOLD,
                text_color=COLOR_TEXT_PRIMARY,
                width=65,
                anchor="e",
            )

            def on_slider_move(slider_pos: float) -> None:
                int_val = int(round(slider_pos / inc) * inc)
                int_val = max(min_v, min(max_v, int_val))
                val_label.configure(text=f"{int_val}{units}")

            def on_slider_release(event: Any) -> None:
                if self._updating_widgets or disabled:
                    return
                int_val = int(round(slider.get() / inc) * inc)
                int_val = max(min_v, min(max_v, int_val))
                self._on_user_value_change(int_val, rail)

            slider = ctk.CTkSlider(
                row_frame,
                from_=min_v,
                to=max_v,
                number_of_steps=max(1, int((max_v - min_v) / inc)),
                command=on_slider_move,
                state="disabled" if disabled else "normal",
            )
            slider.set(cur_v)
            slider.bind("<ButtonRelease-1>", on_slider_release)

            slider.grid(row=0, column=0, sticky="ew", padx=(0, 10))
            val_label.grid(row=0, column=1, sticky="e")
            return slider

        else:
            # Readonly fallback
            units = f" {self.setting.value_units}" if self.setting.value_units else ""
            val_str = f"{current_value}{units}" if current_value is not None else "Read-only"
            ro_lbl = ctk.CTkLabel(
                row_frame,
                text=val_str,
                font=FONT_BODY,
                text_color=COLOR_TEXT_MUTED,
            )
            ro_lbl.grid(row=0, column=0, sticky="w")
            return ro_lbl

    def _on_user_value_change(self, new_val: int, rail: str) -> None:
        """Handle value changes written from UI control."""
        try:
            self.controller.write_setting_value(
                subgroup_guid=self.setting.subgroup_guid,
                setting_guid=self.setting.guid,
                value=new_val,
                rail=rail,
            )
            if rail == "ac":
                self.ac_val = new_val
            else:
                self.dc_val = new_val

            # Handle Linked rails (REQ-11.3)
            if self.is_linked and self.controller.state.has_battery:
                other_rail = "dc" if rail == "ac" else "ac"
                self.controller.write_setting_value(
                    subgroup_guid=self.setting.subgroup_guid,
                    setting_guid=self.setting.guid,
                    value=new_val,
                    rail=other_rail,
                )
                if other_rail == "dc":
                    self.dc_val = new_val
                else:
                    self.ac_val = new_val
                self._update_rail_widget(other_rail, new_val)

            # Update Reset button state
            is_mod = self.controller.state.is_setting_modified(self.setting.guid)
            self.reset_btn.configure(state="normal" if is_mod and not self.setting.is_policy_locked else "disabled")

            if self.on_refresh:
                self.on_refresh()

        except Exception as exc:
            logger.exception("Failed to write setting value: %s", exc)

    def _update_rail_widget(self, rail: str, value: int) -> None:
        """Synchronize UI control with state without triggering recursion."""
        widget = self.dc_widget if rail == "dc" else self.ac_widget
        if not widget:
            return

        self._updating_widgets = True
        try:
            if isinstance(widget, ctk.CTkSlider):
                widget.set(value)
            elif isinstance(widget, ctk.CTkSwitch):
                widget.select() if value == 1 else widget.deselect()
            elif isinstance(widget, ctk.CTkOptionMenu):
                for choice in self.setting.choices:
                    if choice.value_index == value:
                        widget.set(choice.friendly_name)
                        break
        finally:
            self._updating_widgets = False

    def _toggle_link(self) -> None:
        """Toggle linked AC/DC editing mode."""
        self.is_linked = not self.is_linked
        self.link_btn.configure(
            fg_color=COLOR_PRIMARY if self.is_linked else COLOR_SURFACE_SECONDARY
        )
        if self.is_linked and self.ac_val is not None:
            # Sync DC to AC immediately on link
            self._on_user_value_change(self.ac_val, "ac")

    def _on_reset(self) -> None:
        """Reset setting to personality default (REQ-9.3)."""
        if self.setting.is_policy_locked:
            return
        success = self.controller.reset_setting_value(
            subgroup_guid=self.setting.subgroup_guid,
            setting_guid=self.setting.guid,
            rail="both",
        )
        if success:
            s_key = self.setting.guid.lower()
            if self.controller.state.values:
                self.ac_val = self.controller.state.values.ac.get(s_key)
                self.dc_val = self.controller.state.values.dc.get(s_key)
                if self.ac_val is not None:
                    self._update_rail_widget("ac", self.ac_val)
                if self.dc_val is not None:
                    self._update_rail_widget("dc", self.dc_val)

            self.reset_btn.configure(state="disabled")
            if self.on_refresh:
                self.on_refresh()

    def _bind_context_menu(self) -> None:
        """Bind right-click context menu (REQ-10.5, REQ-10.7)."""
        self.bind("<Button-3>", self._popup_context_menu)
        self.title_label.bind("<Button-3>", self._popup_context_menu)
        self.desc_label.bind("<Button-3>", self._popup_context_menu)

    def _popup_context_menu(self, event: Any) -> None:
        """Show context popup at cursor position."""
        menu = self._create_menu()
        menu.tk_popup(event.x_root, event.y_root)

    def _show_context_menu_from_button(self) -> None:
        """Show context popup below More button."""
        x = self.more_btn.winfo_rootx()
        y = self.more_btn.winfo_rooty() + self.more_btn.winfo_height()
        menu = self._create_menu()
        menu.tk_popup(x, y)

    def _create_menu(self) -> tk.Menu:
        """Create standard Tkinter context menu."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copy GUID", command=self._copy_guid)
        menu.add_command(label="Copy powercfg Command", command=self._copy_powercfg)

        is_fav = self.controller.state.is_favorite(self.setting.subgroup_guid, self.setting.guid)
        fav_label = "Remove from Favorites" if is_fav else "Pin to Favorites"
        menu.add_command(label=fav_label, command=self._toggle_favorite)

        if self.doc_url:
            menu.add_command(label="Copy Documentation Link", command=self._copy_doc_link)

        menu.add_separator()
        menu.add_command(label="Apply Value to All Custom Schemes", command=self._bulk_apply_dialog)
        return menu

    def _copy_guid(self) -> None:
        """Copy setting GUID to clipboard (REQ-10.5)."""
        self.clipboard_clear()
        self.clipboard_append(self.setting.guid)

    def _copy_powercfg(self) -> None:
        """Copy ready-to-run powercfg command to clipboard (REQ-10.5)."""
        scheme = self.controller.state.selected_scheme_guid or self.controller.state.active_scheme_guid or "SCHEME_CURRENT"
        sub = self.setting.subgroup_guid
        setting = self.setting.guid
        val = self.ac_val if self.ac_val is not None else 0
        cmd = f"powercfg /setacvalueindex {scheme} {sub} {setting} {val}"
        self.clipboard_clear()
        self.clipboard_append(cmd)

    def _copy_doc_link(self) -> None:
        """Copy documentation link URL to clipboard (REQ-10.7)."""
        if self.doc_url:
            self.clipboard_clear()
            self.clipboard_append(self.doc_url)

    def _toggle_favorite(self) -> None:
        """Toggle favorite status in AppState (REQ-10.4)."""
        self.controller.state.toggle_favorite(self.setting.subgroup_guid, self.setting.guid)
        if self.on_refresh:
            self.on_refresh()

    def _bulk_apply_dialog(self) -> None:
        """Bulk apply this setting's AC/DC values across all custom schemes (REQ-11.4)."""
        custom_schemes = [s for s in self.controller.state.schemes if not s.is_base_default]
        if not custom_schemes:
            return

        # Perform bulk write
        self.controller.apply_setting_to_custom_schemes(
            subgroup_guid=self.setting.subgroup_guid,
            setting_guid=self.setting.guid,
            ac_val=self.ac_val,
            dc_val=self.dc_val,
        )
        if self.on_refresh:
            self.on_refresh()
