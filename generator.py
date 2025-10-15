from diffusers import StableDiffusionPipeline
import torch
from PIL import Image
from kokoro import KPipeline
import soundfile as sf
from pydub import AudioSegment
import unicodedata
from jinja2 import Environment, FileSystemLoader
import genanki
import numpy as np
import argparse
import json
import sys
import io


# TODO Read this example and check if anything could be improved
# https://github.com/kerrickstaley/genanki/blob/main/tests/test_genanki.py


# Generate silence (e.g., 0.3 seconds at 24kHz)
SILENCE_DURATION = 0.3  # seconds
SAMPLE_RATE = 24000
SILENCE = np.zeros(int(SAMPLE_RATE * SILENCE_DURATION))

# Consistent CSS for styling
with open('templates/anki.css', 'r', encoding='utf-8') as css_file:
    ANKI_CSS = css_file.read()


def create_stable_diffusion_pipeline():
    # Set device: use "mps" for M1/M2, "cuda" if available, else "cpu"
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model_id = "dreamlike-art/dreamlike-photoreal-2.0"
    pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16)
    pipe = pipe.to(device)
    return pipe


def generate_image(pipe, prompt, filename):
    image = pipe(prompt).images[0]

    max_size=(384, 384)
    image = image.resize(max_size, Image.LANCZOS)  # LANCZOS = high-quality downsampling

    image.save(filename)


def generate_audio(text, filename):
    # Generate audio using Kokoro
    pipeline = KPipeline(lang_code='e')
    # TODO Randomly use a voice from the available list (https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
    generator = pipeline(text, voice='ef_dora')
    _, _, audio = next(generator)

    # Concatenate silence before and after the audio
    final_audio = np.concatenate([SILENCE, audio, SILENCE])

    # Convert the final audio numpy array to an in-memory WAV file
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, final_audio, SAMPLE_RATE, format='WAV')
    wav_buffer.seek(0)

    # Load the WAV data from memory
    audio = AudioSegment.from_file(wav_buffer, format='wav')

    # Export as MP3
    audio.export(filename, format='mp3')


def generate_file_name(input_str):
    # Normalize and remove accents/diacritics
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    cleaned = []
    for c in nfkd_form:
        if c == ' ':
            cleaned.append('_')
        elif c.isascii() and (c.isalnum()):
            cleaned.append(c)
        elif not unicodedata.combining(c):
            cleaned.append('_')
    # Replace consecutive underscores with a single one
    result = ''.join(cleaned)
    while '__' in result:
        result = result.replace('__', '_')
    return result


class AnkiDeck:
    def __init__(self):
        # Define Anki model (custom card type)
        # TODO Generate a unique model ID
        model_id = 1607392319
        self.model = genanki.Model(
            model_id,
            'SpanishWordExampleModel',  # TODO Rename
            fields=[
                {'name': 'Sentence'},
                {'name': 'Translation'},
                {'name': 'Comment'},
            ],
            templates=[
                {
                    'name': 'Card 1',
                    'qfmt': '<div class="phrase">{{Sentence}}</div>',
                    'afmt': '{{FrontSide}}<hr id="answer"><div class="translation">{{Translation}}</div>{{Comment}}',
                },
            ],
            css=ANKI_CSS
        )

        # TODO Generate a unique deck ID
        self.deck = genanki.Deck(2059400110, 'Spanish Vocabulary: Anhelar')

        self.media_files = []

    def add_note(self, sentence, translation, comment):
        self.deck.add_note(genanki.Note(
            model=self.model,
            fields=[
                sentence,
                translation,
                comment
            ]
        ))

    def add_media_file(self, filename):
        if filename not in self.media_files:
            self.media_files.append(filename)

    def save(self, filename):
        genanki.Package(self.deck, self.media_files).write_to_file(filename)


def main():
    parser = argparse.ArgumentParser(description="Read JSON input from a file.")
    parser.add_argument('input', help='Path to JSON file')
    args = parser.parse_args()

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}", file=sys.stderr)
        sys.exit(1)

    jinja_env = Environment(loader=FileSystemLoader('templates'))
    template_word_comment = jinja_env.get_template('word_comment.html')
    meaning_word_comment = jinja_env.get_template('meaning_comment.html')

    #pipe = create_stable_diffusion_pipeline()

    deck = AnkiDeck()

    # Add card for the word itself
    word_filename = generate_file_name(data['word'])
    # generate_image(pipe, data['image_prompt'], f"{word_filename}.jpg")
    # generate_audio(data['word'], f"{word_filename}.mp3")

    deck.add_note(
        data['word'],
        data['translation'],
        template_word_comment.render(data=data, word_filename=word_filename)
    )
    deck.add_media_file(f"{word_filename}.jpg")
    deck.add_media_file(f"{word_filename}.mp3")

    # Add cards for each meaning
    for m in data['meanings']:
        example = m['example']
        meaning_filename = generate_file_name(example['spanish_phrase'])
        # generate_image(pipe, m['image_prompt'], f"{meaning_filename}.jpg")
        # generate_audio(example['spanish_phrase'], f"{meaning_filename}.mp3")

        deck.add_note(
            example['spanish_phrase'],
            example['english_translation'],
            meaning_word_comment.render(meaning=m, data=data, meaning_filename=meaning_filename)
        )
        deck.add_media_file(f"{meaning_filename}.jpg")
        deck.add_media_file(f"{meaning_filename}.mp3")

    deck.save("anhelar.apkg")


if __name__ == "__main__":
    main()

