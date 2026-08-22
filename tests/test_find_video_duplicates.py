from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pymo.duplicates import videos as video_duplicates
from pymo.duplicates.videos import ProbeInfo
from pymo.action_log import action_log_path
from pymo.collection import CollectionLayout


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
requires_ffmpeg = pytest.mark.skipif(
    not FFMPEG or not FFPROBE,
    reason="real FFmpeg integration test requires ffmpeg and ffprobe",
)


def ffmpeg(*arguments: object) -> None:
    assert FFMPEG
    result = subprocess.run(
        [FFMPEG, "-v", "error", "-y", *(str(item) for item in arguments)],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def make_video(path: Path, *, frequency: int = 440, audio: bool = True) -> None:
    arguments: list[object] = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x48:rate=5:duration=1",
    ]
    if audio:
        arguments.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate=8000:duration=1",
            ]
        )
    arguments.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if audio:
        arguments.extend(["-c:a", "aac", "-shortest"])
    arguments.append(path)
    ffmpeg(*arguments)


@requires_ffmpeg
def test_video_finder_dry_run_apply_and_undo_exact_playback(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    cache = CollectionLayout(tmp_path).video_cache
    base = vids / "base.mp4"
    byte_copy = vids / "byte-copy.mp4"
    remux = vids / "remux.mkv"
    make_video(base)
    shutil.copyfile(base, byte_copy)
    ffmpeg("-i", base, "-map", "0", "-c", "copy", remux)

    dry_run = run_script("find_video_duplicates.py", tmp_path)

    assert dry_run.returncode == 0, dry_run.stdout + dry_run.stderr
    assert "Would move 2 duplicate(s) from 1 group(s)" in dry_run.stdout
    assert "Potentially reclaimable if extra copies were deleted" in dry_run.stdout
    assert "No files are deleted by this tool" in dry_run.stdout
    assert "Fingerprint cache: 0 hit(s), 2 miss(es)" in dry_run.stdout
    assert "inspected 3/3 (100.0%)" in dry_run.stdout
    assert "Fingerprinting 2 uncached candidate content file(s)" in dry_run.stdout
    assert "fingerprint progress 2/2 (100.0%)" in dry_run.stdout
    assert "/s" in dry_run.stdout
    assert not (tmp_path / "dups").exists()
    assert cache.is_file()
    assert not action_log_path(tmp_path).exists()

    applied = run_script("find_video_duplicates.py", tmp_path, "--apply")

    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "Fingerprint cache: 2 hit(s), 0 miss(es)" in applied.stdout
    assert base.exists()
    assert not byte_copy.exists()
    assert not remux.exists()
    assert (tmp_path / "dups" / "vids" / "base_copy(1).mp4").exists()
    assert (tmp_path / "dups" / "vids" / "base_copy(2).mkv").exists()
    assert not (tmp_path / "dups" / "pics").exists()
    assert cache.is_file()
    assert not cache.with_name(f"{cache.name}-wal").exists()
    assert not cache.with_name(f"{cache.name}-shm").exists()
    assert action_log_path(tmp_path).is_file()

    undone = run_script("find_video_duplicates.py", tmp_path, "--undo", "--apply")

    assert undone.returncode == 0, undone.stdout + undone.stderr
    assert base.exists()
    assert byte_copy.exists()
    assert remux.exists()
    assert not (tmp_path / "dups").exists()
    assert cache.is_file()
    assert action_log_path(tmp_path).is_file()


@requires_ffmpeg
def test_video_finder_can_disable_all_cache_reads_and_writes(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    make_video(first)
    shutil.copyfile(first, second)

    result = run_script("find_video_duplicates.py", tmp_path, "--no-cache")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fingerprint cache: 0 hit(s), 1 miss(es); disabled" in result.stdout
    assert not CollectionLayout(tmp_path).video_cache.exists()
    assert not action_log_path(tmp_path).exists()


def test_video_finder_requires_only_vids(tmp_path: Path, run_script) -> None:
    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 2
    assert "missing required folder" in result.stderr
    assert "videos are directly in vids" in result.stderr


@requires_ffmpeg
def test_video_finder_ignores_picture_folder_state(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / ".DS_Store").write_bytes(b"view state")
    (vids / "protected.mp4").write_bytes(b"not inspected")
    (tmp_path / ".pymo.toml").write_text(
        'version = 1\n\n[ignore]\nfiles = ["protected.mp4"]\n',
        encoding="utf-8",
    )
    (tmp_path / "pictures").mkdir()
    dups = tmp_path / "dups"
    dups.mkdir()
    (dups / "pics").write_text("owned by the image finder", encoding="utf-8")

    result = run_script(
        "find_video_duplicates.py", tmp_path, "--show-ignored"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Scanning 0 video(s)" in result.stdout
    assert "Ignored by configuration: 2 path(s)." in result.stdout
    assert "  vids/.DS_Store" in result.stdout
    assert "  vids/protected.mp4" in result.stdout
    assert (vids / "protected.mp4").read_bytes() == b"not inspected"
    assert (dups / "pics").read_text(encoding="utf-8") == "owned by the image finder"


@requires_ffmpeg
def test_video_finder_does_not_match_different_audio(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    make_video(vids / "tone-440.mp4", frequency=440)
    make_video(vids / "tone-880.mp4", frequency=880)

    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would move 0 duplicate(s)" in result.stdout
    assert not (tmp_path / "dups").exists()


@requires_ffmpeg
def test_video_finder_does_not_match_different_playback_timing(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    original = vids / "original.mkv"
    slower = vids / "slower.mkv"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x48:rate=5:duration=1",
        "-c:v",
        "ffv1",
        original,
    )
    ffmpeg(
        "-i",
        original,
        "-vf",
        "setpts=2*PTS",
        "-fps_mode",
        "passthrough",
        "-c:v",
        "ffv1",
        slower,
    )

    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Would move 0 duplicate(s)" in result.stdout


@requires_ffmpeg
def test_video_finder_skips_corrupt_and_multiple_audio_streams(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    (vids / "broken.mp4").write_bytes(
        b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    )
    ambiguous = vids / "multiple-audio.mkv"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=64x48:rate=5:duration=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=8000:duration=1",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=8000:duration=1",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map",
        "2:a:0",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        ambiguous,
    )

    result = run_script("find_video_duplicates.py", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Skipped 2 file(s)" in result.stdout
    assert "multiple audio streams are not yet supported" in result.stdout
    assert "ffprobe rejected the file" in result.stdout
    assert (vids / "broken.mp4").exists()
    assert ambiguous.exists()


@requires_ffmpeg
def test_video_finder_never_overwrites_and_preserves_pics_review(
    tmp_path: Path, run_script
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    make_video(first)
    shutil.copyfile(first, second)
    duplicate_vids = tmp_path / "dups" / "vids"
    duplicate_vids.mkdir(parents=True)
    duplicate_pics = tmp_path / "dups" / "pics"
    duplicate_pics.mkdir()
    protected = duplicate_pics / "review.jpg"
    protected.write_bytes(b"leave this alone")
    occupied = duplicate_vids / "first_copy(1).mp4"
    occupied.write_bytes(b"do not overwrite")

    result = run_script("find_video_duplicates.py", tmp_path, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert occupied.read_bytes() == b"do not overwrite"
    assert (duplicate_vids / "first_copy(2).mp4").exists()
    assert protected.read_bytes() == b"leave this alone"


@requires_ffmpeg
def test_video_duplicate_run_blocks_earlier_rename_undo(
    tmp_path: Path, run_script
) -> None:
    root = tmp_path / "collection"
    vids = root / "vids"
    pics = root / "pics"
    vids.mkdir(parents=True)
    pics.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    make_video(first)
    shutil.copyfile(first, second)

    renamed = run_script("rename_media.py", root, "--apply")
    assert renamed.returncode == 0, renamed.stdout + renamed.stderr
    duplicate_run = run_script("find_video_duplicates.py", root, "--apply")
    assert duplicate_run.returncode == 0, duplicate_run.stdout + duplicate_run.stderr

    blocked = run_script("rename_media.py", root, "--undo", "--apply")
    assert blocked.returncode == 1
    assert "find_video_duplicates" in blocked.stderr

    assert run_script(
        "find_video_duplicates.py", root, "--undo", "--apply"
    ).returncode == 0
    assert run_script("rename_media.py", root, "--undo", "--apply").returncode == 0
    assert first.exists()
    assert second.exists()


def test_video_finder_reports_missing_explicit_ffmpeg(
    tmp_path: Path, run_script
) -> None:
    (tmp_path / "vids").mkdir()
    missing = tmp_path / "not-ffmpeg"

    result = run_script(
        "find_video_duplicates.py",
        tmp_path,
        "--ffmpeg",
        missing,
        "--ffprobe",
        missing,
    )

    assert result.returncode == 2
    assert "not an executable ffmpeg path" in result.stderr


def test_video_cache_keeps_completed_fingerprints_after_interruption(
    tmp_path: Path, monkeypatch
) -> None:
    vids = tmp_path / "vids"
    vids.mkdir()
    first = vids / "first.mp4"
    second = vids / "second.mp4"
    first.write_bytes(b"first content")
    second.write_bytes(b"second content")
    probe = ProbeInfo(
        display_width=64,
        display_height=48,
        duration_us=1_000_000,
        video_start_us=0,
        audio_start_us=None,
        audio_sample_rate=None,
        audio_channels=None,
        audio_layout=None,
        has_audio=False,
    )
    calls = 0

    monkeypatch.setattr(video_duplicates, "resolve_executable", lambda *_: "tool")
    monkeypatch.setattr(video_duplicates, "ffmpeg_version", lambda _: "test-ffmpeg")
    monkeypatch.setattr(
        video_duplicates,
        "discover_videos",
        lambda *_: ([first, second], []),
    )
    monkeypatch.setattr(video_duplicates, "probe_video", lambda *_: probe)

    def interrupt_after_first(*_):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return video_duplicates.DerivedFingerprint("first", 1, 0)

    monkeypatch.setattr(
        video_duplicates, "derive_fingerprint", interrupt_after_first
    )

    with pytest.raises(KeyboardInterrupt):
        video_duplicates.main([str(tmp_path)])

    cached = video_duplicates.load_cached_fingerprints(
        CollectionLayout(tmp_path).video_cache,
        "test-ffmpeg",
    )
    assert cached == {
        video_duplicates.sha256_file(first): video_duplicates.DerivedFingerprint(
            "first", 1, 0
        )
    }


def test_ffmpeg_decode_commands_only_use_local_file_inputs(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_stream(
        command: list[str],
        consume_stdout,
        timeout: int,
        progress_callback=None,
    ) -> None:
        commands.append(command)
        if progress_callback is not None:
            progress_callback()
        if "framehash" in command:
            consume_stdout(
                b"0, 0, 0, 200000, 4, "
                b"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            )
        else:
            consume_stdout(b"\x00\x01\x02\x03")

    monkeypatch.setattr(video_duplicates, "_stream_command", fake_stream)
    local_path = Path("/media-collection/vids/local-video.mp4")
    probe = ProbeInfo(
        display_width=64,
        display_height=48,
        duration_us=1_000_000,
        video_start_us=0,
        audio_start_us=0,
        audio_sample_rate=8_000,
        audio_channels=1,
        audio_layout="mono",
        has_audio=True,
    )

    video_duplicates.derive_fingerprint(local_path, probe, "/usr/bin/ffmpeg", 60)

    assert len(commands) == 2
    for command in commands:
        assert command[command.index("-i") + 1] == str(local_path)
        assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"
        assert not {"avfoundation", "x11grab", "gdigrab"}.intersection(command)
