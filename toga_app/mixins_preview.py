from __future__ import annotations

import json
import math
import random
import re
import time
from collections import Counter

from app_logic import Settings, build_rows
from extractor.frequency import blend_scores_from_terms, precompute_score_terms


class PreviewMixin:
    def _set_zipf_controls_ready(self, ready: bool) -> None:
        self.zipf_min_slider.enabled = ready
        self.zipf_max_slider.enabled = ready
        if ready:
            self.zipf_value_label.text = "Zipf exclusion range"
        else:
            self.zipf_value_label.text = "Zipf exclusion range (Tokenize to use)"

    def _toggle_ignore_words(self, _widget) -> None:
        self._debug("toggle ignore words", enabled=self.enable_ignore_words.value)
        if self.enable_ignore_words.value:
            if self.ignore_words_box not in self.main_box.children:
                self.main_box.add(self.ignore_words_box)
                self._append_log("Ignore words box shown")
        else:
            if self.ignore_words_box in self.main_box.children:
                self.main_box.remove(self.ignore_words_box)
                self._append_log("Ignore words box hidden")
        self._save_persistent_state()
        self._refresh_preview()

    def _on_preview_option_change(self, _widget) -> None:
        self._debug(
            "preview option changed",
            allow_ones=self.allow_ones.value,
            allow_inflections=self.allow_inflections.value,
        )
        self._refresh_preview()

    def _on_ignore_words_change(self, _widget) -> None:
        self._debug("ignore words changed", length=len(self.ignore_words_input.value or ""))
        self._save_persistent_state()

    def _save_persistent_state(self) -> None:
        state = {
            "ignore_words_enabled": bool(self.enable_ignore_words.value),
            "ignore_words_text": self.ignore_words_input.value or "",
        }
        self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_persistent_state(self) -> None:
        if not self.STATE_PATH.exists():
            return
        try:
            state = json.loads(self.STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.ignore_words_input.value = str(state.get("ignore_words_text", ""))
        enabled = bool(state.get("ignore_words_enabled", False))
        self.enable_ignore_words.value = enabled
        if enabled and self.ignore_words_box not in self.main_box.children:
            self.main_box.add(self.ignore_words_box)

    @staticmethod
    def _quantize_slider(value: float) -> float:
        return round(float(value) * 10.0) / 10.0

    def _sync_zipf_labels(self) -> None:
        self.zipf_min_label.text = (
            f"Exclude below (min): {float(self.zipf_min_slider.value):.1f}"
        )
        self.zipf_max_label.text = (
            f"Exclude above (max): {float(self.zipf_max_slider.value):.1f}"
        )

    def _on_zipf_min_change(self, _widget) -> None:
        self._debug("zipf min change", raw=self.zipf_min_slider.value)
        snapped = self._quantize_slider(float(self.zipf_min_slider.value))
        if abs(float(self.zipf_min_slider.value) - snapped) > 1e-9:
            self.zipf_min_slider.value = snapped
            return
        if snapped > float(self.zipf_max_slider.value):
            self.zipf_max_slider.value = snapped
        self._sync_zipf_labels()
        self._refresh_preview()

    def _on_zipf_max_change(self, _widget) -> None:
        self._debug("zipf max change", raw=self.zipf_max_slider.value)
        snapped = self._quantize_slider(float(self.zipf_max_slider.value))
        if abs(float(self.zipf_max_slider.value) - snapped) > 1e-9:
            self.zipf_max_slider.value = snapped
            return
        if snapped < float(self.zipf_min_slider.value):
            self.zipf_min_slider.value = snapped
        self._sync_zipf_labels()
        self._refresh_preview()

    def _on_balance_change(self, _widget) -> None:
        snapped = round(float(self.balance_slider.value) * 100.0) / 100.0
        if abs(float(self.balance_slider.value) - snapped) > 1e-9:
            self.balance_slider.value = snapped
            return
        self.balance_label.text = f"a = {snapped:.2f}"
        self._refresh_preview()

    def _clear_zipf_examples(self) -> None:
        for label in self.zipf_example_labels:
            label.text = "—"

    @staticmethod
    def _clip_bucket_word(word: str, max_chars: int = 11) -> str:
        # Keep bucket columns readable by hiding endings for long words.
        return word if len(word) <= max_chars else word[:max_chars]

    def _update_zipf_examples(self) -> None:
        t0 = time.perf_counter()
        self._debug("zipf examples start", staged_files=len(self.staged_results))
        self._clear_zipf_examples()
        if not self.staged_results:
            self._debug("zipf examples skip", reason="no_staged_results")
            return
        try:
            from wordfreq import zipf_frequency
        except Exception:
            self._append_log("wordfreq not available, Zipf examples skipped")
            self._debug("zipf examples skip", reason="wordfreq_missing")
            return

        merged_lemma_counts: Counter = Counter()
        for _counts, groups in self.staged_results.values():
            for lemma, forms in groups.items():
                merged_lemma_counts[lemma] += sum(forms.values())

        buckets: dict[int, list[str]] = {i: [] for i in range(8)}
        for lemma, _count in merged_lemma_counts.most_common():
            zipf = zipf_frequency(lemma, "pl")
            level = int(math.floor(zipf))
            if level < 0 or level > 7:
                continue
            if len(buckets[level]) < 3 and lemma not in buckets[level]:
                buckets[level].append(lemma)

        for i in range(8):
            clipped = [self._clip_bucket_word(word) for word in buckets[i][:3]]
            self.zipf_example_labels[i].text = "\n\n".join(clipped) if clipped else "—"
        self._debug(
            "zipf examples done",
            seconds=f"{time.perf_counter() - t0:.3f}",
            unique_lemmas=len(merged_lemma_counts),
        )

    def _current_settings(self, limit_value: int | None = None) -> Settings:
        if limit_value is None:
            try:
                limit_value = int(self.limit_input.value or 50)
            except ValueError:
                limit_value = 50
        return Settings(
            start=self.start_input.value,
            end=self.end_input.value,
            limit=limit_value,
            allow_ones=self.allow_ones.value,
            allow_inflections=self.allow_inflections.value,
            use_wordfreq=True,
            min_zipf=float(self.zipf_min_slider.value),
            max_zipf=float(self.zipf_max_slider.value),
            balance_a=float(self.balance_slider.value),
            ignore_patterns=(
                tuple(
                    line.strip().lower()
                    for line in (self.ignore_words_input.value or "").splitlines()
                    if line.strip()
                )
                if self.enable_ignore_words.value
                else ()
            ),
        )

    def _rebuild_preview_cache(self) -> None:
        merged_counts: Counter = Counter()
        merged_groups: dict[str, dict[str, int]] = {}
        for counts, groups in self.staged_results.values():
            merged_counts.update(counts)
            for lemma, forms in groups.items():
                dst = merged_groups.setdefault(lemma, {})
                for form, cnt in forms.items():
                    dst[form] = dst.get(form, 0) + cnt

        lemma_counts = Counter(
            {lemma: sum(forms.values()) for lemma, forms in merged_groups.items()}
        )
        self._preview_terms_cache = {
            "merged_counts": merged_counts,
            "merged_groups": merged_groups,
            "lemma_counts": lemma_counts,
            "token_terms": precompute_score_terms(merged_counts),
            "lemma_terms": precompute_score_terms(lemma_counts),
        }
        self._debug(
            "preview cache rebuilt",
            token_types=len(merged_counts),
            lemmas=len(lemma_counts),
        )

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        chunks = re.split(r"(?<=[.!?])\s+", text)
        return [chunk.strip() for chunk in chunks if chunk.strip()]

    @staticmethod
    def _random_quote_for_word(word: str, sentences: list[str]) -> str:
        if not sentences:
            return ""
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        candidates = [sentence for sentence in sentences if pattern.search(sentence)]
        if not candidates:
            return ""
        return random.choice(candidates)

    @staticmethod
    def _random_quote_for_candidates(candidates: list[str], sentences: list[str]) -> str:
        if not sentences or not candidates:
            return ""
        patterns = [
            re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
            for word in candidates
            if word
        ]
        if not patterns:
            return ""
        hits = [
            sentence for sentence in sentences if any(p.search(sentence) for p in patterns)
        ]
        if not hits:
            return ""
        return random.choice(hits)

    @staticmethod
    def _format_preview_text_table(rows: list[tuple[str, int, str]]) -> str:
        if not rows:
            return ""

        word_col = [word for word, _, _ in rows]
        count_col = [str(count) for _, count, _ in rows]
        score_col = [score for _, _, score in rows]

        word_width = max(len("Word"), *(len(value) for value in word_col))
        count_width = max(len("Count"), *(len(value) for value in count_col))
        score_width = max(len("Score"), *(len(value) for value in score_col))

        def line(word: str, count: str, score: str) -> str:
            return (
                f"{word.ljust(word_width)}  "
                f"{count.rjust(count_width)}  "
                f"{score.rjust(score_width)}"
            )

        lines = [
            line("Word", "Count", "Score"),
            line("-" * word_width, "-" * count_width, "-" * score_width),
        ]
        for word, count, score in rows:
            lines.append(line(word, str(count), score))
        return "\n".join(lines)

    def _refresh_preview(self) -> None:
        if self._preview_refresh_active:
            self._debug("preview refresh skipped", reason="already_active")
            return
        self._preview_refresh_active = True
        t0 = time.perf_counter()
        self._debug("preview refresh start", staged_files=len(self.staged_results))
        if not self.staged_results:
            self.preview_text.value = "Preview updates after tokenization."
            self._debug(
                "preview refresh done",
                seconds=f"{time.perf_counter() - t0:.3f}",
                reason="no_staged_results",
            )
            self._preview_refresh_active = False
            return

        try:
            settings = self._current_settings()
            self._debug(
                "preview settings",
                limit=settings.limit,
                use_wordfreq=settings.use_wordfreq,
                min_zipf=f"{settings.min_zipf:.1f}",
                max_zipf=f"{settings.max_zipf:.1f}",
                balance_a=f"{settings.balance_a:.2f}",
                ignore_patterns=len(settings.ignore_patterns),
            )
            if not self._preview_terms_cache:
                self._rebuild_preview_cache()

            merged_counts = self._preview_terms_cache["merged_counts"]
            merged_groups = self._preview_terms_cache["merged_groups"]
            lemma_counts = self._preview_terms_cache["lemma_counts"]

            if settings.use_wordfreq:
                terms_key = "token_terms" if settings.allow_inflections else "lemma_terms"
                terms = self._preview_terms_cache[terms_key]
                if not settings.allow_ones:
                    source_counts = (
                        merged_counts if settings.allow_inflections else lemma_counts
                    )
                    terms = {
                        word: term
                        for word, term in terms.items()
                        if source_counts.get(word, 0) > 1
                    }
                scored = blend_scores_from_terms(
                    terms,
                    limit=settings.limit,
                    balance_a=settings.balance_a,
                    min_global_zipf=settings.min_zipf,
                    max_global_zipf=settings.max_zipf,
                )
                preview_rows = scored[: min(25, len(scored))]
                rows_len = len(scored)
            else:
                rows = build_rows(merged_counts, merged_groups, settings)
                preview_rows = rows[: min(25, len(rows))]
                rows_len = len(rows)
            self._debug(
                "preview rows ready",
                all_rows=rows_len,
                preview_rows=len(preview_rows),
            )
            if not preview_rows:
                self.preview_text.value = "No words match current filters."
                self._debug(
                    "preview refresh done",
                    seconds=f"{time.perf_counter() - t0:.3f}",
                    reason="empty_after_filter",
                )
                return

            table_rows: list[tuple[str, int, str]] = []
            if settings.use_wordfreq:
                for word, count, score in preview_rows:
                    table_rows.append((word, count, f"{score:.3f}"))
            else:
                for row in preview_rows:
                    score = "" if row.score is None else f"{row.score:.3f}"
                    table_rows.append((row.word, row.count, score))
            self.preview_text.value = self._format_preview_text_table(table_rows)
            self._debug(
                "preview refresh done",
                seconds=f"{time.perf_counter() - t0:.3f}",
                lines=len(table_rows) + 2,
            )
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            self.logger.error("Preview refresh failed: %s\n%s", exc, tb)
            self._append_log(f"Preview error: {exc}")
            self.preview_text.value = f"Preview error: {exc}"
            self._debug("preview refresh error", error=repr(exc))
        finally:
            self._preview_refresh_active = False
