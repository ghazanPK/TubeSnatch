"""Tests that run the real FFmpeg (offline) and, with --live, real YouTube downloads."""

import threading

import pytest

from tubesnatch import convert, engine, ffmpeg

pytestmark = pytest.mark.ffmpeg


@pytest.mark.parametrize("target,quality", [("mp3", 192), ("m4a", 128), ("opus", 96), ("flac", 0), ("wav", 0),
                                            ("mkv", 0), ("mp4", 144), ("webm", 144)])
def test_convert_real(media, tmp_path, target, quality):
    seen = []
    out = convert.convert(str(media), convert.ConvertOptions(target=target, quality=quality,
                                                             outdir=str(tmp_path / "o")),
                          seen.append, threading.Event())
    info = ffmpeg.probe(out)
    assert out.endswith("." + target) and info["has_audio"]
    assert info["has_video"] == (not engine.is_audio(target))
    assert info["duration"] and 2.5 < info["duration"] < 3.6


def test_convert_cancel(media, tmp_path):
    ev = threading.Event()
    ev.set()
    with pytest.raises(ffmpeg.Cancelled):
        convert.convert(str(media), convert.ConvertOptions(target="mp3", outdir=str(tmp_path)), lambda f: None, ev)
    assert not list(tmp_path.glob("*.mp3"))


def test_normalize_in_place(media, tmp_path):
    mp3 = convert.convert(str(media), convert.ConvertOptions(target="mp3", outdir=str(tmp_path)),
                          lambda f: None, threading.Event())
    engine.normalize_audio(mp3, "mp3", 192)
    assert ffmpeg.probe(mp3)["has_audio"]
    assert not list(tmp_path.glob("*norm-tmp*"))


# --------------------------------------------------------------------------- live (opt-in)

ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" — 19 s, first YouTube video


@pytest.mark.live
def test_live_probe_and_trimmed_mp3(tmp_path):
    r = engine.probe(ZOO)
    assert r.kind == "video" and r.entries[0].id == "jNQXAC9IVRw" and r.entries[0].heights
    res = engine.download(ZOO, engine.JobOptions(outdir=str(tmp_path), fmt="mp3", quality=128, trim=(2, 8),
                                                 normalize=True), lambda p: None, threading.Event())
    d = ffmpeg.probe(res.path)["duration"]
    assert res.path.endswith(".mp3") and 5 < d < 7.5


@pytest.mark.live
def test_live_mp4_h264(tmp_path):
    res = engine.download(ZOO, engine.JobOptions(outdir=str(tmp_path), fmt="mp4", quality=240),
                          lambda p: None, threading.Event())
    assert res.path.endswith(".mp4") and ffmpeg.probe(res.path)["has_video"]
