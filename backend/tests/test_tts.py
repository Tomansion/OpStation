"""Speech rendering. Skipped when the voice models are not downloaded."""
import pytest

from opstation.config import difficulty as load_difficulty
from opstation.generate.plan import BeatSpec
from opstation.generate.schedule import SENTENCE_END, Scheduler
from opstation.generate.tts import PiperTTS, duration_of
from opstation.station import station as load_station

FOUR_SENTENCES = (
    "Door Control, Construction. We are venting Extension Epsilon in two minutes. "
    "H5 stays closed until I clear it. No exceptions."
)


@pytest.fixture(scope="module")
def piper():
    engine = PiperTTS()
    if not engine.available():
        pytest.skip("piper or its voice models are not installed")
    try:
        engine.model_for("en_US-joe-medium")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(str(exc))
    return engine


def test_a_pause_is_inserted_between_sentences(piper, tmp_path):
    """A radio message has no transcript and is heard once, so sentences running
    into each other are unintelligible rather than merely hard."""
    tight = PiperTTS(sentence_gap_seconds=0.0)
    tight._cache = piper._cache
    spaced = PiperTTS(sentence_gap_seconds=1.0)
    spaced._cache = piper._cache

    short = tight.say(FOUR_SENTENCES, "en_US-joe-medium", tmp_path / "tight.wav")
    long = spaced.say(FOUR_SENTENCES, "en_US-joe-medium", tmp_path / "spaced.wav")
    breaks = len(SENTENCE_END.findall(FOUR_SENTENCES)) - 1
    assert breaks == 3
    # Piper's synthesis carries noise scales, so two renders of one sentence are
    # not identical in length. The tolerance covers that drift, not the gap.
    assert long - short == pytest.approx(breaks * 1.0, abs=0.6)
    assert long > short


def test_the_estimate_covers_the_real_audio(piper, tmp_path):
    """The scheduler prices radio messages before they exist. If it prices them
    too low, the scenario passes validation and then fails V7 in the re-check
    against real durations -- after the audio has been rendered."""
    diff = load_difficulty()
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.diff = diff
    gap = float(diff.get("tts_sentence_gap_seconds", 1.0))
    engine = PiperTTS(sentence_gap_seconds=gap)
    engine._cache = piper._cache

    samples = [
        FOUR_SENTENCES,
        "Cargo. D12 open for the pallet run.",
        "Security here. Someone was let into the service corridor an hour ago and I "
        "need a name for the report. Who authorised that door? I am not asking twice.",
    ]
    for index, text in enumerate(samples):
        beat = BeatSpec(key=f"b{index}", thread_key="t", phase=1, actor_type="cargo",
                        channel="radio", kind="instruction", text=text)
        estimate = Scheduler.read_cost(scheduler, beat)
        real = engine.say(text, "en_US-joe-medium", tmp_path / f"s{index}.wav")
        real_cost = diff.read_cost(text, real)
        assert estimate >= real_cost, (
            f"estimate {estimate}s under-prices {real_cost}s of real audio: {text[:50]!r}"
        )


def test_the_system_voice_is_band_limited(piper, tmp_path):
    """Without the filter the station's automated voice is simply a seventh
    person, and provenance questions get muddier."""
    from opstation.config import voices as load_voices
    from opstation.generate.tts import apply_filter

    voices = load_voices()
    try:
        piper.model_for(voices.voice_for("system"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(str(exc))
    path = tmp_path / "system.wav"
    piper.say("Pressure alarm. Sector integrity compromised.",
              voices.voice_for("system"), path)
    before = path.read_bytes()
    apply_filter(path, voices.ffmpeg_filter("pa_intercom"))
    after = path.read_bytes()
    assert after != before
    assert duration_of(path) > 0
