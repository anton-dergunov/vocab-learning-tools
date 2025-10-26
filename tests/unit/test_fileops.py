import pytest

from vocabgen import fileops


def test_atomic_write_creates_file(tmp_path):
    file_path = tmp_path / "test.txt"
    fileops.atomic_write(file_path, "hello world")
    assert file_path.exists()
    assert file_path.read_text() == "hello world"


def test_atomic_write_overwrites_existing(tmp_path):
    file_path = tmp_path / "data.txt"
    file_path.write_text("old")
    fileops.atomic_write(file_path, "new")
    assert file_path.read_text() == "new"


def test_append_to_file_adds_newline(tmp_path):
    file_path = tmp_path / "out.txt"
    fileops.append_to_file(file_path, "line1")
    fileops.append_to_file(file_path, "line2\n")
    text = file_path.read_text().splitlines()
    assert text == ["line1", "line2"]


def test_read_text_reads_correctly(tmp_path):
    f = tmp_path / "readme.txt"
    f.write_text("abc")
    assert fileops.read_text(f) == "abc"


def test_backup_file_creates_copy(tmp_path):
    orig = tmp_path / "sample.txt"
    orig.write_text("hello")
    bkp = fileops.backup_file(orig, keep_timestamp=False)
    assert bkp.exists()
    assert bkp.read_text() == "hello"
    assert bkp.name.endswith(".bak")


def test_backup_file_raises_for_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        fileops.backup_file(tmp_path / "nonexistent.txt")


def test_slugify():
    assert fileops.slugify_filename("cómodo") == "comodo"
    assert fileops.slugify_filename("  Qué linda sako!  ") == "que_linda_sako"
    assert fileops.slugify_filename("你好") == "ni_hao"
    assert fileops.slugify_filename("Привет мир") == "privet_mir"
    assert fileops.slugify_filename("a / b \\ c") == "a_b_c"
    assert fileops.slugify_filename("a ? b :") == "a_b"
