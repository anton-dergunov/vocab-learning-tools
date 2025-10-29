import soundfile as sf
from pydub import AudioSegment
import numpy as np
import io


# Generate silence (e.g., 0.3 seconds at 24kHz)
SILENCE_DURATION = 0.3  # seconds
SAMPLE_RATE = 24000
SILENCE = np.zeros(int(SAMPLE_RATE * SILENCE_DURATION))
# TODO Consider exposing these parameters in the config


# TODO Add type annotation & documentation
def wrap_audio_with_silence(audio):
    # Concatenate silence before and after the audio
    return np.concatenate([SILENCE, audio, SILENCE])


def save_audio_to_mp3_file(audio, filename):
    # Convert the audio array to an in-memory WAV file
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, audio, SAMPLE_RATE, format='WAV')
    wav_buffer.seek(0)

    # Load the WAV data from memory
    audio = AudioSegment.from_file(wav_buffer, format='wav')

    # Export as MP3
    audio.export(filename, format='mp3')
