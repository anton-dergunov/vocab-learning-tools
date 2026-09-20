"""What a clip is stored as: Opus, encoded here from the provider's uncompressed answer.

**Measured, blind, in `experiments/pronunciation-encoding/`.** Cloud TTS's `MP3` is 32 kbps for a
Gemini voice and 64 for a WaveNet one, and in a blind test of one performance encoded five ways every
file the listener flagged was the 32 kbps MP3 — *"obviously compressed, much smaller range"* — while
Opus at ~30 kbps was indistinguishable from the uncompressed master. So the provider is asked for the
**master** (`LINEAR16`, 24 kHz PCM, 384 kbps) and the compression happens here, which buys the one
thing asking for `OGG_OPUS` cannot: the bitrate is ours to set. The API meters characters, never
bytes, so the bigger download costs nothing.

**Only an uncompressed answer is encoded.** A provider that already returned MP3 — Cloudflare's Aura
— has its bytes stored exactly as they arrived: re-encoding a lossy stream into another lossy codec
adds a second generation of artifacts to save a few kilobytes, which is the opposite of the point.

`soundfile` rather than an ffmpeg binary: it ships libsndfile in its wheels, so the server image needs
no system package, and libsndfile 1.2 writes Ogg Opus directly.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

# Everything the providers Acervo speaks to can answer with, and whether it is already compressed.
UNCOMPRESSED = ("audio/wav", "audio/x-wav", "audio/wave")
STORED_MIME = "audio/ogg"
MASTER_MIME = "audio/flac"

# libsndfile's compression level runs from 0.0 (largest) to 1.0 (smallest), and for Opus it lands on
# a bitrate. Measured on a 5.2 s Spanish sentence at 24 kHz mono: 0.0 → 225 kbps, 0.3 → 159,
# 0.5 → 116, **0.8 → 51**, default → 32, 1.0 → 7.
#
# 0.8 it is. The blind test found ~32 kbps already indistinguishable from the master, so this is a
# deliberate half-again of headroom over the point where one listener stopped hearing a difference —
# a sentence costs about 33 KB rather than 21, which is still a sixth of the uncompressed master and
# less than the MP3 the same listener could hear at a glance. It is one number: lower it to trade the
# margin back for space.
COMPRESSION = 0.8


class CannotEncode(Exception):
    """The audio arrived uncompressed and this deployment cannot compress it.

    Deliberately loud rather than a fallback that stores the master: a silent fall back to 384 kbps
    would multiply every clip by twelve and only show up as a full disk, weeks later, on a phone.
    """


def compact(data: bytes, mime: str) -> tuple[bytes, str]:
    """The bytes to keep, or to send, and the type to call them. Compressed answers pass through.

    Both callers want the same thing for different reasons. A stored clip is compressed because it is
    replicated to every device; a **selection** is compressed because it is downloaded and then thrown
    away, and 384 kbps of WAV over a phone connection for a phrase nobody keeps is the worst of both.
    Encoding a second of speech costs milliseconds either way.
    """
    if mime not in UNCOMPRESSED:
        return data, mime
    return to_opus(data), STORED_MIME


def master(data: bytes, mime: str) -> tuple[bytes, str]:
    """The bytes to keep as a **take**, losslessly, and the type to call them.

    The opposite trade to `compact`, for the opposite reason. A clip is downloaded before it can be
    heard, so it is worth compressing; a take is about to be time-stretched, pitch-shifted and mixed
    into a track that is itself encoded, so compressing it here would put a lossy generation in front
    of every one of those. FLAC keeps the master exactly and costs about half of WAV.

    A compressed answer still passes through untouched, for `compact`'s reason: wrapping a lossy
    stream in a lossless container preserves the artefacts and adds the bytes back.
    """
    if mime not in UNCOMPRESSED:
        return data, mime
    return to_flac(data), MASTER_MIME


def to_flac(wav: bytes) -> bytes:
    """One WAV in, one FLAC out, sample for sample."""
    try:
        import soundfile
    except ImportError as missing:  # pragma: no cover — declared in requirements/server.txt
        raise CannotEncode(f"soundfile is not installed, so audio cannot be stored: {missing}") from None
    try:
        samples, rate = soundfile.read(io.BytesIO(wav), dtype="int16", always_2d=True)
        out = io.BytesIO()
        with soundfile.SoundFile(
            out, "w", samplerate=rate, channels=samples.shape[1], format="FLAC", subtype="PCM_16"
        ) as writing:
            writing.write(samples)
    except Exception as unreadable:  # noqa: BLE001 — every decoder failure means the same thing here
        raise CannotEncode(f"that audio could not be re-encoded: {unreadable}") from None
    return out.getvalue()


def to_opus(wav: bytes, compression: float = COMPRESSION) -> bytes:
    """One WAV in, one Ogg Opus out, at the same sample rate the voice produced."""
    soundfile = _soundfile()
    try:
        samples, rate = soundfile.read(io.BytesIO(wav), dtype="int16", always_2d=True)
        return _opus(samples, rate, compression)
    except Exception as unreadable:  # noqa: BLE001 — every decoder failure means the same thing here
        raise CannotEncode(f"that audio could not be re-encoded: {unreadable}") from None


# The rest a reader would want between two passages. A voice's own leading and trailing silence is
# a few tens of milliseconds and differs from call to call, so on its own it leaves the seams uneven;
# this is what makes them even.
PASSAGE_GAP = 0.12


@dataclass(frozen=True)
class Joined:
    data: bytes
    mime: str
    # `(start, end)` in seconds of each input, in the order given. They are *known* rather than
    # aligned: the file is built here from one recording per passage, so where each one sits is
    # arithmetic on the sample counts, exact to the sample.
    spans: tuple[tuple[float, float], ...]


def concat(recordings: Sequence[bytes], gap: float = PASSAGE_GAP) -> Joined:
    """Several recordings of one voice, one after another, as one Ogg Opus file.

    They must share a sample rate and a channel count, which a voice held fixed for a story does and
    a mixture of voices might not — that is refused rather than resampled, because a rate that
    differs is a sign the recordings are not from the voice they were meant to be. A recording that
    arrived compressed is decoded to be joined, which is a second lossy generation; the one caller
    that can meet it (an English voice that answers MP3) has no alternative, since a file cannot be
    joined without being decoded.
    """
    if not recordings:
        raise CannotEncode("there is nothing to join")
    soundfile = _soundfile()
    try:
        decoded = [soundfile.read(io.BytesIO(data), dtype="int16", always_2d=True) for data in recordings]
    except Exception as unreadable:  # noqa: BLE001 — every decoder failure means the same thing here
        raise CannotEncode(f"that audio could not be read: {unreadable}") from None
    rate, channels = decoded[0][1], decoded[0][0].shape[1]
    if any(one[1] != rate or one[0].shape[1] != channels for one in decoded):
        raise CannotEncode("the recordings differ in sample rate or channels and cannot be joined")

    import numpy

    silence = numpy.zeros((round(rate * gap), channels), dtype="int16")
    pieces, spans, at = [], [], 0
    for index, (samples, _rate) in enumerate(decoded):
        if index:
            pieces.append(silence)
            at += len(silence)
        pieces.append(samples)
        spans.append((round(at / rate, 3), round((at + len(samples)) / rate, 3)))
        at += len(samples)
    try:
        return Joined(data=_opus(numpy.concatenate(pieces), rate, COMPRESSION), mime=STORED_MIME,
                      spans=tuple(spans))
    except Exception as unwritable:  # noqa: BLE001 — same as above, for the encoder
        raise CannotEncode(f"that audio could not be re-encoded: {unwritable}") from None


def _soundfile():
    try:
        import soundfile
    except ImportError as missing:  # pragma: no cover — declared in requirements/server.txt
        raise CannotEncode(f"soundfile is not installed, so audio cannot be stored: {missing}") from None
    return soundfile


def _opus(samples, rate: int, compression: float) -> bytes:
    import soundfile

    out = io.BytesIO()
    with soundfile.SoundFile(
        out, "w", samplerate=rate, channels=samples.shape[1], format="OGG", subtype="OPUS",
        compression_level=compression,
    ) as writing:
        writing.write(samples)
    return out.getvalue()
