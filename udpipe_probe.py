from __future__ import annotations

from ufal.udpipe import Model, Pipeline


TEXT = "rozumiecie słuchacie rozumiemy zapomnisz bać widzicie rozpoznajesz"
MODEL_PATH = "data/udpipe/polish-pdb-ud-2.5-191206.udpipe"


def main() -> None:
    model = Model.load(MODEL_PATH)
    if model is None:
        raise RuntimeError(f"Failed to load model: {MODEL_PATH}")
    pipeline = Pipeline(model, "tokenize", Pipeline.DEFAULT, Pipeline.DEFAULT, "conllu")
    conllu = pipeline.process(TEXT)
    for line in conllu.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 6 and parts[0].isdigit():
            form, lemma, upos, feats = parts[1], parts[2], parts[3], parts[5]
            print(f"{form}\t{lemma}\t{upos}\t{feats}")


if __name__ == "__main__":
    main()
