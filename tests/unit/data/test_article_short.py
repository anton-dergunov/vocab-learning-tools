import pytest
from vocabgen.data.article_short import ArticleShort


@pytest.fixture
def sample_article_text():
    return """##### **la balsa** 🛶
*raft*
> El río tenía una **balsa**. - The river had a raft.
> Usamos la **balsa** para cruzar el lago.
"""


def test_parse_valid_article(sample_article_text):
    art = ArticleShort.parse_from_markdown(sample_article_text)
    assert art.headword == "la balsa"
    assert art.emoji == "🛶"
    assert art.translation == "raft"
    assert len(art.examples) == 2
    assert art.examples[0].phrase.startswith("El río tenía")
    assert art.examples[0].translation == "The river had a raft."
    assert art.to_markdown().strip() == sample_article_text.strip()


def test_parse_article_without_emoji():
    text = """##### **el oso**
*bear*
> El **oso** duerme en la cueva.
"""
    art = ArticleShort.parse_from_markdown(text)
    assert art.headword == "el oso"
    assert art.emoji is None
    assert art.translation == "bear"
    assert art.examples[0].translation is None or "cueva" in art.examples[0].phrase


def test_missing_translation_line_raises():
    text = """##### **la luna** 🌕
"""
    with pytest.raises(ValueError, match="Missing translation line"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_heading_missing_hashes():
    # Missing '#####' prefix
    text = """**la luna** 🌙
*moon*
"""
    with pytest.raises(ValueError, match="Invalid heading line"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_heading_too_many_hashes():
    # Wrong number of '#' characters (4 instead of 5)
    text = """#### **la luna** 🌙
*moon*
"""
    with pytest.raises(ValueError, match="Invalid heading line"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_heading_missing_stars():
    # Missing bold '**' around the word
    text = """##### la luna 🌙
*moon*
"""
    with pytest.raises(ValueError, match="Invalid heading line"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_heading_no_word():
    # Empty bold section
    text = """##### **** 🌙
*moon*
"""
    with pytest.raises(ValueError, match="Invalid heading line"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_heading_missing_space_after_hashes():
    # Missing space after ##### (must be "##### **word**")
    text = """#####**la luna** 🌙
*moon*
"""
    with pytest.raises(ValueError, match="Invalid heading line"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_translation_raises():
    text = """##### **la luna** 🌕
moon
"""
    with pytest.raises(ValueError, match="Invalid translation line"):
        ArticleShort.parse_from_markdown(text)


def test_blank_translation_raises_during_parsing():
    text = """##### **la luna** 🌕
* *
"""
    with pytest.raises(ValueError, match="Empty translation"):
        ArticleShort.parse_from_markdown(text)


def test_invalid_example_line_raises():
    text = """##### **la luna** 🌕
*moon*
El cielo está oscuro.
"""
    with pytest.raises(ValueError, match="Invalid example line"):
        ArticleShort.parse_from_markdown(text)


def test_example_without_english_translation():
    text = """##### **el gato** 🐱
*cat*
> El **gato** duerme.
"""
    art = ArticleShort.parse_from_markdown(text)
    assert art.examples[0].phrase == "El **gato** duerme."
    assert art.examples[0].translation is None


def test_validate_rejects_empty_fields():
    art = ArticleShort(
        headword="",
        emoji=None,
        translation="word",
        examples=[],
        raw_markdown="",
    )
    with pytest.raises(ValueError, match="Empty headword"):
        art.validate()

    art = ArticleShort(
        headword="hola",
        emoji=None,
        translation="",
        examples=[],
        raw_markdown="",
    )
    with pytest.raises(ValueError, match="Empty translation"):
        art.validate()

    bad_example = ArticleShort.Example(phrase=" ", translation=None)
    art = ArticleShort(
        headword="hola",
        emoji=None,
        translation="hello",
        examples=[bad_example],
        raw_markdown="",
    )
    with pytest.raises(ValueError, match="Empty example text"):
        art.validate()


def test_to_markdown_validates_manually_constructed_article():
    art = ArticleShort(
        headword="hola",
        emoji=None,
        translation=" ",
        examples=[],
        raw_markdown="",
    )

    with pytest.raises(ValueError, match="Empty translation"):
        art.to_markdown()
