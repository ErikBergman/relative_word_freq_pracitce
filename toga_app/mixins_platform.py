from __future__ import annotations

import sys
from pathlib import Path


class PlatformMixin:
    def _set_macos_app_identity(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from rubicon.objc import ObjCClass

            process_info = ObjCClass("NSProcessInfo").processInfo
            process_info.setProcessName_(self.formal_name)

            ns_app = ObjCClass("NSApplication").sharedApplication
            ns_image = ObjCClass("NSImage").alloc().initWithContentsOfFile_(
                str(Path("data/book_icon2.png").resolve())
            )
            if ns_image is not None:
                ns_app.setApplicationIconImage_(ns_image)
        except Exception:
            # Non-fatal: this is a best-effort tweak for script mode on macOS.
            pass

    def _set_preview_monospace_font(self) -> None:
        # Use widget-level font settings first.
        self.preview_text.font_family = [
            "SF Mono",
            "Menlo",
            "Monaco",
            "Courier New",
            "monospace",
        ]
        self.preview_text.font_size = 11

        # macOS backend can ignore style fonts for read-only multiline widgets.
        # Force a native monospace font on the underlying NSTextView when available.
        if sys.platform != "darwin":
            return
        try:
            from rubicon.objc import ObjCClass

            ns_font = ObjCClass("NSFont")
            font = ns_font.fontWithName_size_("Menlo", 11.0)
            if font is None:
                font = ns_font.monospacedSystemFontOfSize_weight_(11.0, 0.0)

            native = self.preview_text._impl.native
            if hasattr(native, "setFont_"):
                native.setFont_(font)
            if hasattr(native, "documentView"):
                doc_view = native.documentView()
                if doc_view is not None and hasattr(doc_view, "setFont_"):
                    doc_view.setFont_(font)
        except Exception as exc:
            self._debug("preview monospace fallback failed", error=repr(exc))
