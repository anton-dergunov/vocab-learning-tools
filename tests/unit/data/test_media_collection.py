import pytest

from vocabgen.data.media_collection import MediaCollection


def test_media_collection_adds_lists_and_overwrites_bytes(tmp_path):
    images = MediaCollection(tmp_path / "cache", "images")

    path = images.add_from_bytes("anorar.jpg", b"first")

    assert path == tmp_path / "cache" / "images" / "anorar.jpg"
    assert images.exists("anorar.jpg")
    assert images.list_files() == [path]
    assert path.read_bytes() == b"first"

    with pytest.raises(FileExistsError):
        images.add_from_bytes("anorar.jpg", b"second")

    images.add_from_bytes("anorar.jpg", b"second", overwrite=True)
    assert path.read_bytes() == b"second"


def test_media_collection_copies_existing_file(tmp_path):
    source = tmp_path / "source.mp3"
    source.write_bytes(b"audio")
    audio = MediaCollection(tmp_path / "cache", "audio")

    copied = audio.add_from_path(source, "anorar.mp3")

    assert copied.read_bytes() == b"audio"
    assert copied != source


@pytest.mark.parametrize("unsafe_name", ["../escape.jpg", "/tmp/escape.jpg", ""])
def test_media_collection_rejects_unsafe_names(tmp_path, unsafe_name):
    images = MediaCollection(tmp_path, "images")

    with pytest.raises(ValueError, match="single relative file name"):
        images.path_for(unsafe_name)


@pytest.mark.parametrize("unsafe_kind", ["../images", "/tmp/images", ""])
def test_media_collection_rejects_unsafe_kind(tmp_path, unsafe_kind):
    with pytest.raises(ValueError, match="single relative directory name"):
        MediaCollection(tmp_path, unsafe_kind)
