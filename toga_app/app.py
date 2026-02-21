from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import toga
from toga.constants import Direction
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .mixins_debug import DebugMixin
from .mixins_platform import PlatformMixin
from .mixins_preview import PreviewMixin
from .mixins_run import RunMixin


class PolishVocabApp(
    DebugMixin,
    PlatformMixin,
    PreviewMixin,
    RunMixin,
    toga.App,
):
    ZIPF_MIN = 0.0
    ZIPF_MAX = 7.0
    STATE_PATH = Path(".cache/app_toga_state.json")

    def startup(self) -> None:
        self.files: list[Path] = []
        self.staged_results: dict[str, tuple[Counter, dict[str, dict[str, int]]]] = {}
        self.staged_sentences: dict[str, list[str]] = {}
        self.is_running = False
        self.cancel_requested = False
        self.step_totals = {"clean": 1, "tokenize": 0, "lemmatize": 0, "count": 1}
        self.logger = logging.getLogger("app_toga")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        out_dir = Path("output_html")
        out_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(out_dir / "app_toga.log", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        self.logger.addHandler(file_handler)
        self._debug_seq = 0
        self._preview_refresh_active = False
        self._preview_terms_cache: dict[str, object] = {}

        self.file_list = toga.MultilineTextInput(
            readonly=True,
            placeholder="Drag files here or use Browse…",
            style=Pack(flex=1, height=120),
        )
        browse_btn = toga.Button("Browse…", on_press=self.browse, style=Pack(margin_top=5))
        self.clear_files_btn = toga.Button(
            "Clear list",
            on_press=self.clear_files,
            style=Pack(margin_top=5, margin_left=8),
        )
        file_actions_row = toga.Box(style=Pack(direction=ROW))
        file_actions_row.add(browse_btn)
        file_actions_row.add(self.clear_files_btn)

        self.start_input = toga.TextInput(
            value="Download mp3 file:", style=Pack(flex=1)
        )
        self.end_input = toga.TextInput(value="<hr />", style=Pack(flex=1))

        self.limit_input = toga.TextInput(value="50", style=Pack(width=120))
        self.balance_slider = toga.Slider(value=0.5, min=0.0, max=1.0, style=Pack(flex=1))
        self.balance_slider.on_change = self._on_balance_change
        self.balance_label = toga.Label("a = 0.50")

        self.allow_ones = toga.Switch(
            "Include words with frequency 1", on_change=self._on_preview_option_change
        )
        self.allow_inflections = toga.Switch(
            "Include inflections in list", on_change=self._on_preview_option_change
        )
        self.enable_ignore_words = toga.Switch(
            "Ignore words", on_change=self._toggle_ignore_words
        )
        self.ignore_words_input = toga.MultilineTextInput(
            placeholder="One pattern per line, wildcards allowed (e.g. *ing, rp*)",
            on_change=self._on_ignore_words_change,
            style=Pack(height=120),
        )
        self.ignore_words_box = toga.Box(style=Pack(direction=COLUMN, margin_top=8))
        self.ignore_words_box.add(
            toga.Label("Ignore patterns (one per row, supports * and ?)")
        )
        self.ignore_words_box.add(self.ignore_words_input)

        self.zipf_min_slider = toga.Slider(
            value=1.0, min=self.ZIPF_MIN, max=self.ZIPF_MAX, style=Pack(flex=1)
        )
        self.zipf_min_slider.on_change = self._on_zipf_min_change
        self.zipf_max_slider = toga.Slider(
            value=7.0, min=self.ZIPF_MIN, max=self.ZIPF_MAX, style=Pack(flex=1)
        )
        self.zipf_max_slider.on_change = self._on_zipf_max_change
        self.zipf_value_label = toga.Label("Zipf exclusion range (Tokenize to use)")
        self.zipf_min_label = toga.Label("Exclude below (min): 1.0")
        self.zipf_max_label = toga.Label("Exclude above (max): 7.0")
        self.zipf_scale_row = toga.Box(style=Pack(direction=ROW, margin_top=4))
        self.zipf_example_row = toga.Box(style=Pack(direction=ROW, margin_top=2))
        self.zipf_example_labels: list[toga.Label] = []
        for i in range(8):
            self.zipf_scale_row.add(toga.Label(str(i), style=Pack(flex=1, font_size=10)))
            label = toga.Label("—", style=Pack(flex=1, font_size=9))
            self.zipf_example_labels.append(label)
            self.zipf_example_row.add(label)
        self.zipf_box = toga.Box(style=Pack(direction=COLUMN, margin_top=8))
        self.zipf_box.add(self.zipf_value_label)
        self.zipf_box.add(self.zipf_min_label)
        self.zipf_box.add(self.zipf_min_slider)
        self.zipf_box.add(self.zipf_max_label)
        self.zipf_box.add(self.zipf_max_slider)
        self.zipf_box.add(self.zipf_scale_row)
        self.zipf_box.add(self.zipf_example_row)
        self._set_zipf_controls_ready(False)

        self.progress = toga.ProgressBar(max=1, value=0, style=Pack(flex=1))
        self.log_box = toga.MultilineTextInput(
            readonly=True, style=Pack(flex=1, height=130, margin_top=8)
        )
        self.tokenize_btn = toga.Button(
            "Tokenize", on_press=self.start_tokenize, style=Pack(margin_top=8)
        )
        self.export_btn = toga.Button(
            "Create Lists + Export",
            on_press=self.start_export,
            style=Pack(margin_top=8),
        )
        self.export_btn.enabled = False
        self.cancel_btn = toga.Button(
            "Cancel", on_press=self.cancel, style=Pack(margin_top=8, margin_left=8)
        )
        # Backward compatibility for tests/helpers that still reference start_btn.
        self.start_btn = self.tokenize_btn

        rules_box = toga.Box(style=Pack(direction=COLUMN, flex=1, margin_right=10))
        rules_box.add(toga.Label("Start marker"))
        rules_box.add(self.start_input)
        rules_box.add(toga.Label("End marker", style=Pack(margin_top=8)))
        rules_box.add(self.end_input)

        token_options_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        token_options_box.add(toga.Label("Tokenization options"))
        token_options_box.add(self.enable_ignore_words)

        top_row = toga.Box(style=Pack(direction=ROW, margin_top=8))
        top_row.add(rules_box)
        top_row.add(token_options_box)

        export_options_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        export_options_box.add(toga.Label("Listing + export options"))
        export_options_box.add(self.allow_ones)
        export_options_box.add(self.allow_inflections)
        export_options_box.add(
            toga.Label("Balance (absolute vs relative)", style=Pack(margin_top=8))
        )
        export_options_box.add(self.balance_label)
        export_options_box.add(self.balance_slider)
        export_options_box.add(
            toga.Label("Max number of phrases per document", style=Pack(margin_top=8))
        )
        export_options_box.add(self.limit_input)

        self.tokenize_button_row = toga.Box(style=Pack(direction=ROW))
        self.tokenize_button_row.add(self.tokenize_btn)
        self.export_button_row = toga.Box(style=Pack(direction=ROW))
        self.export_button_row.add(self.export_btn)

        self.tokenization_section_label = toga.Label(
            "1) Tokenization",
            style=Pack(font_size=16, font_weight="bold"),
        )
        self.listing_separator = toga.Box(
            style=Pack(height=1, background_color="#b8b8b8", margin_top=12, margin_bottom=6)
        )
        self.listing_section_label = toga.Label(
            "2) Listing + Export",
            style=Pack(font_size=16, font_weight="bold"),
        )

        main_box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        main_box.add(self.tokenization_section_label)
        main_box.add(toga.Label("Files", style=Pack(margin_top=4)))
        main_box.add(self.file_list)
        main_box.add(file_actions_row)
        main_box.add(top_row)
        main_box.add(self.tokenize_button_row)

        main_box.add(self.listing_separator)
        main_box.add(self.listing_section_label)
        main_box.add(export_options_box)
        main_box.add(self.zipf_box)
        main_box.add(self.export_button_row)

        main_box.add(self.progress)
        main_box.add(toga.Label("Log", style=Pack(margin_top=8)))
        main_box.add(self.log_box)

        self.preview_box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        self.preview_box.add(toga.Label("Top List Preview"))
        self.preview_text = toga.MultilineTextInput(
            readonly=True,
            value="Preview updates after tokenization.",
            style=Pack(
                flex=1,
                font_family=["SF Mono", "Menlo", "Monaco", "Courier New", "monospace"],
                font_size=11,
            ),
        )
        self.preview_box.add(self.preview_text)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_box = main_box
        self.root_scroll = toga.ScrollContainer(
            content=main_box,
            horizontal=False,
            vertical=True,
            style=Pack(flex=1),
        )
        self.split = toga.SplitContainer(
            direction=Direction.VERTICAL,
            content=[(self.root_scroll, 0.60), (self.preview_box, 0.40)],
            style=Pack(flex=1),
        )
        self.main_window.content = self.split
        self.main_window.size = (1400, 900)
        self.main_window.show()
        self._set_preview_monospace_font()
        self._set_macos_app_identity()

        # Best-effort drag-and-drop support (platform dependent).
        try:
            self.main_window.on_drop = self.on_drop
        except Exception:
            pass
        self._listing_controls = [
            self.allow_ones,
            self.allow_inflections,
            self.balance_slider,
            self.limit_input,
            self.export_btn,
        ]
        self._set_listing_controls_ready(False)
        self._load_persistent_state()
        self._append_log("GUI initialized")
        self._debug("startup complete", ignore_enabled=self.enable_ignore_words.value)

    def _set_listing_controls_ready(self, ready: bool) -> None:
        for widget in self._listing_controls:
            widget.enabled = ready
        if not ready:
            self.export_btn.enabled = False
        self._set_zipf_controls_ready(ready)


def main() -> None:
    PolishVocabApp(
        "Polish Vocabulary Extractor",
        "org.example.polishvocab",
        app_name="PolishVocabularyExtractor",
        icon=Path("data/book_icon2.png"),
    ).main_loop()
