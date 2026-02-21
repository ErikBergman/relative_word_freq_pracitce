from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OpusMtTranslator:
    model_name: str = "Helsinki-NLP/opus-mt-pl-en"
    batch_size: int = 16
    max_new_tokens: int = 200

    def __post_init__(self) -> None:
        self._tokenizer = None
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return
        from transformers import MarianMTModel, MarianTokenizer

        self._tokenizer = MarianTokenizer.from_pretrained(self.model_name)
        self._model = MarianMTModel.from_pretrained(self.model_name)

    def translate_many(self, sentences: list[str]) -> list[str]:
        self._ensure_loaded()
        if not sentences:
            return []

        assert self._tokenizer is not None
        assert self._model is not None

        output: list[str] = []
        for i in range(0, len(sentences), self.batch_size):
            batch = sentences[i : i + self.batch_size]
            encoded = self._tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            generated = self._model.generate(
                **encoded,
                max_new_tokens=self.max_new_tokens,
            )
            output.extend(
                self._tokenizer.batch_decode(generated, skip_special_tokens=True)
            )
        return output

