from layout import flag_truncation, running_text
from hit import sentence_of, token_at
from segment import pysbd_es, rules


def word(text, line, x, brk="space"):
    return {"text": text, "confidence": 0.9, "line": line, "break": brk,
            "polygon": [[x, line * 0.1], [x + 0.1, line * 0.1], [x + 0.1, line * 0.1 + 0.05],
                        [x, line * 0.1 + 0.05]]}


def test_a_word_hyphenated_across_lines_is_one_token_with_both_polygons():
    layout = {"words": [word("Se", 0, 0.0), word("trans-", 0, 0.2, "eol"), word("formó", 1, 0.0),
                        word("así.", 1, 0.2, "eol")]}
    result = running_text(layout)
    assert result["text"] == "Se transformó así."
    joined = [t for t in result["tokens"] if t["text"] == "transformó"]
    assert len(joined) == 1 and len(joined[0]["polygons"]) == 2


def test_a_hyphen_before_a_capital_is_kept():
    layout = {"words": [word("Atelman-", 0, 0.0, "eol"), word("Fourcade", 1, 0.0)]}
    assert running_text(layout)["text"] == "Atelman- Fourcade"


def test_rules_split_on_terminal_punctuation_but_not_abbreviations_or_numbers():
    text = "Llegó en 1.506 a Roma. Ver pp. 85-110 del Sr. Pelli. ¿Por qué tomó esa decisión el rey? Nadie lo sabe"
    spans = [text[s:e] for s, e in rules(text)]
    assert spans == ["Llegó en 1.506 a Roma.", "Ver pp. 85-110 del Sr. Pelli.",
                     "¿Por qué tomó esa decisión el rey?", "Nadie lo sabe"]


def test_pysbd_spans_index_the_original_text():
    text = "Primera frase. Segunda frase."
    assert [text[s:e] for s, e in pysbd_es(text)] == ["Primera frase.", "Segunda frase."]


def test_truncation_flags_a_lowercase_start_and_an_unterminated_end():
    text = "mer contingente llegó. Seis años más tarde, después de"
    flags = flag_truncation(text, rules(text))
    assert flags[0]["truncatedStart"] and not flags[0]["truncatedEnd"]
    assert flags[-1]["truncatedEnd"]


def test_a_tap_just_outside_a_word_still_selects_it():
    layout = {"words": [word("hola", 0, 0.0), word("mundo.", 0, 0.2)]}
    result = running_text(layout)
    index = token_at(result["tokens"], (0.31, 0.06))  # just right of "mundo."
    assert result["tokens"][index]["text"] == "mundo."
    assert sentence_of(rules(result["text"]), result["tokens"][index]) == 0
