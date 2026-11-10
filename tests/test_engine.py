import pytest

from tubesnatch import engine
from tubesnatch.engine import JobOptions, build_args, parse_time


def opts(**kw):
    return JobOptions(outdir="/out", **kw)


def args_str(**kw):
    return " ".join(build_args(opts(**kw)))


def test_audio_mp3_bitrate():
    a = build_args(opts(fmt="mp3", quality=192))
    assert a[a.index("--audio-format") + 1] == "mp3"
    assert a[a.index("--audio-quality") + 1] == "192K"
    assert "--embed-thumbnail" in a and "--embed-metadata" in a


@pytest.mark.parametrize("fmt", ["flac", "wav"])
def test_lossless_audio_has_no_quality(fmt):
    a = build_args(opts(fmt=fmt, quality=320))
    assert "--audio-quality" not in a
    assert a[a.index("--audio-format") + 1] == fmt


def test_wav_and_webm_skip_cover_art():
    assert "--embed-thumbnail" not in build_args(opts(fmt="wav"))
    assert "--embed-thumbnail" not in build_args(opts(fmt="webm"))


def test_video_mp4_prefers_h264_at_height():
    a = build_args(opts(fmt="mp4", quality=720))
    assert a[a.index("-S") + 1] == "res:720,vcodec:h264,acodec:aac,ext:mp4:m4a"
    assert a[a.index("--merge-output-format") + 1] == "mp4"


def test_video_best_mkv():
    a = build_args(opts(fmt="mkv", quality=0))
    assert a[a.index("-S") + 1] == "res"


def test_trim_sections_and_filename():
    a = build_args(opts(fmt="mp3", trim=(80, 225)))
    assert a[a.index("--download-sections") + 1] == "*80-225"
    assert "--force-keyframes-at-cuts" in a
    assert "[01m20s-03m45s]" in a[a.index("-o") + 1]


def test_trim_to_end_without_accurate_cuts():
    a = build_args(opts(fmt="mp4", trim=(30, None), accurate_cuts=False))
    assert a[a.index("--download-sections") + 1] == "*30-inf"
    assert "--force-keyframes-at-cuts" not in a


def test_split_chapters_template():
    a = build_args(opts(fmt="mp3", split_chapters=True, filename_prefix="003 - "))
    assert "--split-chapters" in a
    assert "chapter:003 - %(title)s/%(section_number)02d - %(section_title)s.%(ext)s" in a


def test_trim_wins_over_chapters():
    assert "--split-chapters" not in build_args(opts(fmt="mp3", split_chapters=True, trim=(0, 10)))


def test_subtitles_embed_and_file():
    a = build_args(opts(fmt="mp4", subtitles="embed", sub_langs="en,de"))
    assert "--embed-subs" in a and a[a.index("--sub-langs") + 1] == "en,de"
    b = build_args(opts(fmt="mp3", subtitles="embed"))  # audio can't hold subs → .srt
    assert "--embed-subs" not in b and "--convert-subs" in b
    assert "--write-subs" not in build_args(opts(fmt="mp4", subtitles="embed"), with_subs=False)


def test_sponsorblock_and_rate_limit():
    s = args_str(fmt="mp3", sponsorblock=True, rate_limit="2M")
    assert f"--sponsorblock-remove {engine.SPONSORBLOCK_CATEGORIES}" in s
    assert "--limit-rate 2M" in s


def test_args_parse_with_ytdlp():
    """Every combination must be accepted by yt-dlp's own option parser."""
    import yt_dlp

    for fmt in engine.VIDEO_FORMATS + engine.AUDIO_FORMATS:
        o = opts(fmt=fmt, quality=720 if not engine.is_audio(fmt) else 192, trim=(5, 9), subtitles="embed",
                 sponsorblock=True, rate_limit="1M")
        yt_dlp.parse_options(build_args(o))
        yt_dlp.parse_options(build_args(opts(fmt=fmt, split_chapters=True)))


@pytest.mark.parametrize("text,expected", [
    ("", None), ("90", 90), ("1:30", 90), ("01:02:03", 3723), ("1:30.5", 90.5), (" 2:00 ", 120),
])
def test_parse_time(text, expected):
    assert parse_time(text) == expected


@pytest.mark.parametrize("bad", ["abc", "1::2", "1:2:3:4", "-5"])
def test_parse_time_invalid(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


def test_fmt_duration():
    assert engine.fmt_duration(None) == "—"
    assert engine.fmt_duration(0) == "0:00"
    assert engine.fmt_duration(3723) == "1:02:03"


def test_valid_rate():
    assert engine.valid_rate("") and engine.valid_rate("750K") and engine.valid_rate("1.5M")
    assert not engine.valid_rate("fast")


def test_archive_key():
    e = engine.Entry(url="u", id="abc", extractor="Youtube")
    assert e.archive_key == "youtube abc"
    assert engine.Entry(url="u").archive_key == ""


def test_playlist_folder_sanitizes():
    p = engine.playlist_folder("/base", 'My: "Best" / Mix?')
    assert "/" not in p.split("base", 1)[1].lstrip("/\\")
