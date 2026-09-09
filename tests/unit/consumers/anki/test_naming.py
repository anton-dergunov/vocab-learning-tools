from acervo.consumers.anki.naming import slugify_filename


def test_slugify_filename_folds_accents_and_punctuation():
    assert slugify_filename("cómodo") == "comodo"
    assert slugify_filename("  Qué linda sako!  ") == "que_linda_sako"
    assert slugify_filename("a / b \\ c") == "a_b_c"
    assert slugify_filename("a ? b :") == "a_b"


def test_slugify_filename_transliterates_non_latin_scripts():
    assert slugify_filename("你好") == "ni_hao"
    assert slugify_filename("Привет мир") == "privet_mir"
