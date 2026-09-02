"""Text to speech, at generation time only.

Piper, local and offline, with one pinned voice per actor type. Wrapped behind a
small interface so a cloud provider can be swapped in later without touching the
pipeline (spec 14.1).

The `system` voice is band-limited through an intercom filter. Without it the
station's automated voice is simply a seventh person and provenance gets
muddier; with it, "the station said it" is audibly different from "somebody said
it". ffmpeg does the filtering when it is on PATH; a pure-Python biquad
equivalent runs when it is not, so a missing system binary cannot silently
produce an unfiltered system voice.
"""
from __future__ import annotations

import array
import math
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Voices, voices as load_voices
from ..models import Scenario
from ..paths import ASSETS_DIR

VOICES_DIR = ASSETS_DIR / "voices"


class TTSError(RuntimeError):
    pass


@dataclass
class TextToSpeech:
    """The interface the pipeline depends on, so a cloud provider can be swapped
    in later without touching anything else."""

    def say(self, text: str, voice: str, dest: Path, speaker_id: int | None = None) -> float:
        """Render `text` to `dest` and return its duration in seconds."""
        raise NotImplementedError

    def available(self) -> bool:
        return True


#: Sentinels, so the silence can be sized after the first chunk reveals the
#: sample rate.
_SILENCE = object()
_DOOR_PAUSE = object()

DOOR_TOKEN = re.compile(r"\b([DH]\d{1,2})\b")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [part for part in SENTENCE_SPLIT.split(text.strip()) if part]


def split_doors(sentence: str) -> list[tuple[str, bool]]:
    """Break a sentence into prose and door-name fragments, in order."""
    out: list[tuple[str, bool]] = []
    cursor = 0
    for match in DOOR_TOKEN.finditer(sentence):
        before = sentence[cursor:match.start()].strip()
        if before:
            out.append((before, False))
        # "D 7" rather than "D7": the letter and the number are what the player
        # has to match against the label on the map, so they are said separately.
        out.append((f"{match.group(1)[0]} {match.group(1)[1:]}", True))
        cursor = match.end()
    rest = sentence[cursor:].strip()
    if rest:
        out.append((rest, False))
    return out or [(sentence, False)]


@dataclass
class PiperTTS(TextToSpeech):
    voices_dir: Path = VOICES_DIR
    #: All three come from config/difficulty.json.
    sentence_gap_seconds: float = 1.0
    door_pause_seconds: float = 0.25
    door_length_scale: float = 1.3
    _cache: dict = field(default_factory=dict, repr=False)

    def model_for(self, voice: str) -> Path:
        path = self.voices_dir / f"{voice}.onnx"
        if not path.exists():
            raise TTSError(
                f"voice model missing: {path}. Run `python3 assets/download_voices.py`."
            )
        return path

    def available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return self.voices_dir.exists()

    def _voice(self, voice: str):
        if voice not in self._cache:
            from piper import PiperVoice

            self._cache[voice] = PiperVoice.load(str(self.model_for(voice)))
        return self._cache[voice]

    def _config(self, is_door: bool, speaker_id: int | None):
        from piper import SynthesisConfig

        length_scale = self.door_length_scale if is_door and self.door_length_scale != 1.0 else None
        if length_scale is None and speaker_id is None:
            return None
        return SynthesisConfig(speaker_id=speaker_id, length_scale=length_scale)

    def say(self, text: str, voice: str, dest: Path, speaker_id: int | None = None) -> float:
        """Render one message: a pause between sentences, and the door names
        given weight.

        Two problems, both from the same source. A radio message has no
        transcript and is heard exactly once, so anything the ear misses is gone
        for good. Sentences running together are unintelligible rather than
        merely hard -- the gap is what separates "H5 stays closed" from "until I
        clear it". And a door name is simultaneously the most important word in
        the sentence and the shortest, so at conversational speed "close D7 for
        the pressure check" spends almost no time on the only part the player has
        to act on.

        So door names are synthesised on their own, slower, with a short pause
        either side. It sounds like an operator enunciating a number, which is
        what it is.
        """
        loaded = self._voice(voice)
        dest.parent.mkdir(parents=True, exist_ok=True)

        rendered: list = []
        spec = None
        for index, sentence in enumerate(split_sentences(text)):
            if index:
                rendered.append(_SILENCE)
            for fragment, is_door in split_doors(sentence):
                chunks = list(loaded.synthesize(fragment, self._config(is_door, speaker_id)))
                if not chunks:
                    continue
                spec = spec or chunks[0]
                if is_door:
                    rendered.append(_DOOR_PAUSE)
                rendered.append(b"".join(c.audio_int16_bytes for c in chunks))
                if is_door:
                    rendered.append(_DOOR_PAUSE)
        if spec is None:
            raise TTSError(f"{voice} produced no audio for {text[:60]!r}")

        frame = spec.sample_width * spec.sample_channels
        gap = b"\x00" * (int(self.sentence_gap_seconds * spec.sample_rate) * frame)
        pause = b"\x00" * (int(self.door_pause_seconds * spec.sample_rate) * frame)
        with wave.open(str(dest), "wb") as wav:
            wav.setnchannels(spec.sample_channels)
            wav.setsampwidth(spec.sample_width)
            wav.setframerate(spec.sample_rate)
            for piece in rendered:
                if piece is _SILENCE:
                    wav.writeframes(gap)
                elif piece is _DOOR_PAUSE:
                    wav.writeframes(pause)
                else:
                    wav.writeframes(piece)
        return duration_of(dest)


def duration_of(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return round(wav.getnframes() / float(wav.getframerate()), 2)


# ------------------------------------------------------------------- filtering

def apply_filter(path: Path, ffmpeg_args: str) -> None:
    """Band-limit and compress in place."""
    if shutil.which("ffmpeg"):
        tmp = path.with_suffix(".filtered.wav")
        command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path)]
        command += _split_ffmpeg_args(ffmpeg_args)
        command.append(str(tmp))
        subprocess.run(command, check=True)
        tmp.replace(path)
        return
    _intercom_python(path)


def _split_ffmpeg_args(args: str) -> list[str]:
    import shlex

    return shlex.split(args)


def _intercom_python(path: Path, low: float = 400.0, high: float = 3400.0) -> None:
    """The pa_intercom filter without ffmpeg: one-pole high-pass, one-pole
    low-pass, then soft compression. Not bit-identical to ffmpeg's chain, but it
    produces the same audible result -- telephone-band, hard-limited -- which is
    what the filter is for."""
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())
    if params.sampwidth != 2:
        return
    samples = array.array("h")
    samples.frombytes(frames)
    rate = params.framerate

    hp_a = math.exp(-2.0 * math.pi * low / rate)
    lp_a = math.exp(-2.0 * math.pi * high / rate)
    out = array.array("h", bytes(len(samples) * 2))
    prev_in = prev_hp = lp = 0.0
    for i, raw in enumerate(samples):
        x = raw / 32768.0
        hp = hp_a * (prev_hp + x - prev_in)
        prev_in, prev_hp = x, hp
        lp = lp + (1.0 - lp_a) * (hp - lp)
        # Soft-knee compression, roughly threshold -18 dB at 6:1, then make-up.
        magnitude = abs(lp)
        threshold = 0.126
        if magnitude > threshold:
            magnitude = threshold + (magnitude - threshold) / 6.0
            lp_c = math.copysign(magnitude, lp)
        else:
            lp_c = lp
        value = int(max(-1.0, min(1.0, lp_c * 1.6 * 2.2)) * 32767)
        out[i] = value
    with wave.open(str(path), "wb") as wav:
        wav.setparams(params)
        wav.writeframes(out.tobytes())


# -------------------------------------------------------------------- pipeline

def render_scenario(
    scenario: Scenario,
    directory: Path,
    *,
    engine: TextToSpeech | None = None,
    voices: Voices | None = None,
    progress=None,
) -> int:
    """Render every radio message and radio challenge prompt, and write the real
    durations back into the scenario. `read_cost` depends on them, so the
    pipeline re-validates afterwards (spec 12.1 step 5)."""
    from ..config import difficulty as _difficulty

    diff_now = _difficulty()
    engine = engine or PiperTTS(
        sentence_gap_seconds=float(diff_now.get("tts_sentence_gap_seconds", 1.0)),
        door_pause_seconds=float(diff_now.get("tts_door_pause_seconds", 0.25)),
        door_length_scale=float(diff_now.get("tts_door_length_scale", 1.3)),
    )
    voice_map = voices or load_voices(scenario.language)
    if not engine.available():
        raise TTSError(
            "no TTS engine available. `pip install piper-tts` and "
            "`python3 assets/download_voices.py`."
        )
    audio_dir = directory / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    actors = scenario.actors_by_id
    count = 0

    items: list[tuple[str, str, str]] = [
        (m.id, m.actor_id, m.text) for m in scenario.messages if m.channel == "radio"
    ]
    items += [
        (c.id, c.actor_id, c.prompt)
        for c in scenario.all_challenges if c.channel == "radio"
    ]

    rendered: dict[str, tuple[str, float]] = {}
    for item_id, actor_id, text in items:
        actor = actors.get(actor_id)
        if actor is None:
            continue
        dest = audio_dir / f"{item_id}.wav"
        seconds = engine.say(text, actor.voice, dest, speaker_id=actor.speaker)
        post = voice_map.post_filter_for(actor.type)
        if post:
            apply_filter(dest, voice_map.ffmpeg_filter(post))
            seconds = duration_of(dest)
        rendered[item_id] = (f"audio/{dest.name}", seconds)
        count += 1
        if progress:
            progress("tts", f"{item_id} ({actor.type}) {seconds:.1f}s")

    from ..config import difficulty as load_difficulty

    diff = load_difficulty()
    for msg in scenario.messages:
        if msg.id in rendered:
            msg.audio, msg.audio_duration = rendered[msg.id]
            msg.read_cost = diff.read_cost(msg.text, msg.audio_duration)
    for ch in scenario.all_challenges:
        if ch.id in rendered:
            ch.audio, ch.audio_duration = rendered[ch.id]
    return count
