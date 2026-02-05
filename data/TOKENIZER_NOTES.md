# Stanza Evaluation Notes

## Strengths
- Produces rich morphological features (e.g., case, number, gender, person).
- Useful for distinguishing preposition-governed cases (e.g., genitive vs instrumental).
- Provides lemmas and POS tags out of the box.

## Shortcomings / Caveats
- Ambiguous forms can be misclassified (e.g., **czasami** can be tagged as a noun instead of an adverb depending on context).
- Errors may appear in short or decontextualized snippets where the model has limited cues.
- Model loading is relatively heavy and can be slow on first run.
- Outputs depend on the tokenization path; errors there can cascade into POS/morph mistakes.

## Practical Takeaways
- Stanza is strong for case detection on inflected nouns/pronouns.
- For highly ambiguous tokens, cross-check with context or another tagger if precision matters.
- Keep sample sentences natural and contextual to get the best tagging results.
