"""Generate a scenario from the command line.

    python -m opstation.generate --duration 1620 --finale invasion
    python -m opstation.generate --dry-run     # skip TTS, keep it fast
"""
from __future__ import annotations

import argparse
import sys

from .. import paths
from .pipeline import Generator, publish


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="opstation.generate")
    ap.add_argument("--duration", type=int, default=1620, help="session length in seconds")
    ap.add_argument("--threads", type=int, default=5, help="incident threads")
    ap.add_argument("--everyday", type=int, default=None, help="everyday exchanges")
    ap.add_argument("--temptations", type=int, default=4)
    ap.add_argument("--finale", default=None,
                    help="invasion | hull_breach | reactor_emergency | station_contamination")
    ap.add_argument("--theme", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--no-audio", action="store_true", help="skip the TTS pass")
    ap.add_argument("--no-publish", action="store_true")
    args = ap.parse_args(argv)

    def progress(stage: str, message: str) -> None:
        print(f"  {stage:<12} {message}", flush=True)

    from .llm import LLM

    generator = Generator(llm=LLM(model=args.model or ""), progress=progress)
    print(f"generating with {generator.llm.model}", flush=True)
    result = generator.generate(
        duration=args.duration, finale=args.finale, theme=args.theme,
        threads=args.threads, seed=args.seed, everyday=args.everyday,
        temptations=args.temptations,
    )
    print()
    print(f"scenario   {result.scenario.scenario_id}  {result.scenario.name!r}")
    print(f"validator  {result.report.summary()}")
    for key, value in result.report.stats.items():
        print(f"    {key:<24}{value}")
    if not result.report.ok:
        print("\nerrors:")
        for finding in result.report.errors[:40]:
            print(f"    {finding}")

    if args.no_publish:
        return 0 if result.report.ok else 1

    directory = publish(result)
    print(f"\nwritten to {directory}")

    if args.no_audio or not result.report.ok:
        if args.no_audio and result.report.ok:
            print("no audio rendered — the scenario is not playable until it has some")
        return 0 if result.report.ok else 1

    # Steps 4 and 5 of the pipeline: render, write the real durations back, and
    # re-validate. read_cost depends on audio length, so the timing rules have to
    # be re-checked against the real files rather than the estimates.
    from ..validator import validate
    from .tts import render_scenario, TTSError

    print("rendering audio ...")
    try:
        rendered = render_scenario(
            result.scenario, directory,
            progress=lambda stage, message: print(f"  {stage:<12} {message}", flush=True),
        )
    except TTSError as exc:
        print(f"  TTS unavailable: {exc}")
        print("  the scenario is stored but cannot be played until its audio exists")
        return 1
    print(f"  {rendered} files")

    # Step 5: re-check the timing rules against the real durations, and settle
    # the difference the estimate could not know about.
    from .repair import reflow_for_audio

    for line in reflow_for_audio(result.scenario):
        print(f"  reflow      {line}")
    result.scenario.dump(directory / "scenario.json")
    report = validate(result.scenario, audio_dir=directory / "audio")
    report.dump(directory / "validation.json")
    print(f"revalidated  {report.summary()}")
    if not report.ok:
        for finding in report.errors[:20]:
            print(f"    {finding}")
        result.scenario.status = "invalid"
        result.scenario.dump(directory / "scenario.json")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
