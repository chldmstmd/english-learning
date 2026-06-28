from functools import lru_cache

import spacy


@lru_cache(maxsize=1)
def get_nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        return nlp


def tokenize(raw_text: str) -> tuple[list[dict], list[dict], int]:
    """
    Returns (tokens, sentences, word_count).
    Each token: {text, pos, lemma, index, sentence_index, is_punct, is_alpha, ws}
    Each sentence: {index, text}
    word_count = number of alpha tokens
    """
    nlp = get_nlp()
    doc = nlp(raw_text)

    tokens: list[dict] = []
    sentences: list[dict] = []
    word_count = 0

    for sent_idx, sent in enumerate(doc.sents):
        sentences.append({"index": sent_idx, "text": sent.text.strip()})
        for token in sent:
            if token.is_space:
                continue
            tokens.append({
                "text": token.text,
                "pos": token.tag_,
                "lemma": (token.lemma_ or token.text).lower(),
                "index": token.i,
                "sentence_index": sent_idx,
                "is_punct": token.is_punct,
                "is_alpha": token.is_alpha,
                "ws": token.whitespace_,
            })
            if token.is_alpha:
                word_count += 1

    return tokens, sentences, word_count
