"""What a clip is stored as: Opus, encoded from the provider's uncompressed master.

The measurement behind the choice is `experiments/pronunciation-encoding/`; what is pinned here is
the rule that came out of it — an uncompressed answer is compressed, and a compressed one is not
touched, because re-encoding a lossy stream buys kilobytes and costs a second generation of
artifacts.
"""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from acervo.pronunciation.encode import CannotEncode, PASSAGE_GAP, STORED_MIME, compact, concat, to_opus

RATE = 24_000
SECONDS = 1.5


def spoken_wav(rate: int = RATE) -> bytes:
    """A second and a half of tone, which is enough for a codec to have an opinion about."""
    frames = bytearray()
    for index in range(int(rate * SECONDS)):
        value = int(12_000 * math.sin(2 * math.pi * 220 * index / rate))
        frames += struct.pack("<h", value)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


def test_an_uncompressed_master_is_stored_as_ogg_opus():
    master = spoken_wav()
    kept, mime = compact(master, "audio/wav")
    assert mime == STORED_MIME == "audio/ogg"
    assert kept[:4] == b"OggS"
    # Under a fifth of the master. The blind test's sentence went from 242 KB to 33 KB.
    assert len(kept) < len(master) / 5


def test_the_bitrate_is_a_number_rather_than_whatever_the_provider_felt_like():
    """The reason the master is requested at all: Google's `OGG_OPUS` is 28–35 kbps, take it or
    leave it, and this is the knob that replaces it."""
    master = spoken_wav()
    lean = to_opus(master, compression=1.0)
    default = to_opus(master)
    generous = to_opus(master, compression=0.3)
    assert len(lean) < len(default) < len(generous)


def test_something_already_compressed_is_stored_exactly_as_it_arrived():
    for mime in ("audio/mpeg", "audio/ogg", "audio/flac"):
        assert compact(b"already-compressed", mime) == (b"already-compressed", mime)


def test_audio_that_cannot_be_read_says_so_rather_than_storing_a_master():
    """Loud rather than a fallback: silently keeping 384 kbps would multiply every clip by twelve
    and show up as a full phone weeks later."""
    with pytest.raises(CannotEncode):
        compact(b"RIFFnot-really-a-wav", "audio/wav")


def test_the_voices_sample_rate_is_kept_whatever_it_is():
    """A provider that answers at 48 kHz — Opus's own rate — must not be resampled on the way in."""
    kept, _mime = compact(spoken_wav(48_000), "audio/wav")
    assert kept[:4] == b"OggS"


# ── joining recordings ──────────────────────────────────────────────────────


def _seconds(ogg: bytes) -> float:
    import soundfile

    with soundfile.SoundFile(io.BytesIO(ogg)) as read:
        return len(read) / read.samplerate


def test_recordings_are_joined_into_one_file_and_each_says_where_it_sits():
    joined = concat([spoken_wav(), spoken_wav(), spoken_wav()])

    assert joined.mime == STORED_MIME and joined.data[:4] == b"OggS"
    assert joined.spans[0][0] == 0
    # Each is SECONDS long and a rest of PASSAGE_GAP separates them: the spans are arithmetic on the
    # samples, so they are exact and not an estimate.
    for (start, end), (next_start, _) in zip(joined.spans, joined.spans[1:]):
        assert end - start == pytest.approx(SECONDS, abs=0.001)
        assert next_start - end == pytest.approx(PASSAGE_GAP, abs=0.001)
    assert _seconds(joined.data) == pytest.approx(joined.spans[-1][1], abs=0.05)


def test_one_recording_joins_to_itself():
    joined = concat([spoken_wav()])

    assert joined.spans == ((0.0, SECONDS),)


def test_recordings_at_different_sample_rates_are_refused_not_resampled():
    with pytest.raises(CannotEncode, match="sample rate"):
        concat([spoken_wav(24_000), spoken_wav(16_000)])


def test_nothing_to_join_and_unreadable_audio_are_refused():
    with pytest.raises(CannotEncode):
        concat([])
    with pytest.raises(CannotEncode, match="could not be read"):
        concat([spoken_wav(), b"not audio"])
