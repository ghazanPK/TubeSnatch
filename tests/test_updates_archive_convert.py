from pathlib import Path

import pytest

from tubesnatch import convert, updates
from tubesnatch.archive import Archive


# --------------------------------------------------------------------------- versions

@pytest.mark.parametrize("a,b", [
    ("v1.1.1", "1.1.0"), ("1.10.0", "1.9.9"), ("2026.11.10", "2026.10.26"),
    ("2026.11.10.233421.dev0", "2026.11.10"), ("2026.11.10.233421.dev0", "2026.10.26"),
])
def test_is_newer(a, b):
    assert updates.is_newer(a, b)
    assert not updates.is_newer(b, a)


def test_same_version_not_newer():
    assert not updates.is_newer("v1.1.0", "1.1.0")


def test_check_engine_picks_nightly_and_ejs_pin(monkeypatch):
    def fake(url, timeout=15):
        if url.endswith("/yt-dlp/json"):
            return {"info": {"version": "2026.10.26"},
                    "releases": {"2026.10.26": [{}], "2026.11.9.1.dev0": [{}], "2026.11.10.2.dev0": [{}],
                                 "2026.12.1.dev0": [{"yanked": True}]}}
        assert "/yt-dlp/2026.11.10.2.dev0/json" in url
        return {"info": {"requires_dist": ["yt-dlp-ejs==0.9.1; extra == 'default'"]}}

    monkeypatch.setattr(updates, "_get_json", fake)
    monkeypatch.setattr(updates, "installed_version", lambda pkg: "2026.10.26")
    info = updates.check_engine("nightly")
    assert info.latest == "2026.11.10.2.dev0" and info.ejs_pin == "0.9.1" and info.update_available


def test_check_app_reads_release(monkeypatch):
    monkeypatch.setattr(updates, "__version__", "1.1.0")
    monkeypatch.setattr(updates, "_get_json", lambda url, timeout=15: {
        "tag_name": "v1.1.3", "body": "notes", "html_url": "h",
        "assets": [{"name": "TubeSnatch-1.1.3-win64-portable.zip", "browser_download_url": "z", "size": 5},
                   {"name": "SHA256SUMS.txt", "browser_download_url": "s"}]})
    info = updates.check_app("x/y")
    assert info.version == "1.1.3" and info.zip_url == "z" and info.sums_url == "s"
    monkeypatch.setattr(updates, "__version__", "1.1.3")
    assert updates.check_app("x/y") is None


def test_swap_command_runs_from_staged_build(tmp_path):
    staged = tmp_path / "w" / "extracted" / "TubeSnatch"
    cmd = updates.swap_command(staged, Path(r"C:\Apps\TubeSnatch"), 4242, relaunch=True)
    assert cmd[0] == str(staged / "TubeSnatch.exe") and cmd[1:3] == ["-m", "tubesnatch._swap"]
    assert "4242" in cmd and cmd[-1] == "--relaunch"
    assert "--relaunch" not in updates.swap_command(staged, Path("x"), 1, relaunch=False)


def test_mirror_replaces_and_prunes(tmp_path):
    from tubesnatch._swap import mirror

    src, dst = tmp_path / "new", tmp_path / "old"
    (src / "Lib" / "pkg-2.0").mkdir(parents=True)
    (src / "Lib" / "pkg-2.0" / "a.py").write_text("new")
    (src / "TubeSnatch.exe").write_text("exe2")
    (dst / "Lib" / "pkg-1.0").mkdir(parents=True)
    (dst / "Lib" / "pkg-1.0" / "a.py").write_text("old")
    (dst / "TubeSnatch.exe").write_text("exe1")
    (dst / "stale.txt").write_text("x")
    mirror(src, dst)
    assert (dst / "TubeSnatch.exe").read_text() == "exe2"
    assert (dst / "Lib" / "pkg-2.0" / "a.py").read_text() == "new"
    assert not (dst / "Lib" / "pkg-1.0").exists() and not (dst / "stale.txt").exists()


# --------------------------------------------------------------------------- archive

def test_archive_roundtrip(tmp_path):
    a = Archive(tmp_path / "a.txt")
    assert "youtube x" not in a
    a.add("youtube x")
    a.add("youtube x")
    assert "YouTube X" in a and len(a) == 1
    assert Archive(tmp_path / "a.txt").__contains__("youtube x")
    a.clear()
    assert len(a) == 0 and not (tmp_path / "a.txt").exists()


# --------------------------------------------------------------------------- converter

def test_convert_output_path_avoids_overwrite(tmp_path):
    src = tmp_path / "song.mp3"
    src.write_bytes(b"x")
    o = convert.ConvertOptions(target="mp3")
    assert convert.output_path(str(src), o).name == "song (converted).mp3"
    o2 = convert.ConvertOptions(target="flac", outdir=str(tmp_path / "out"))
    assert convert.output_path(str(src), o2) == tmp_path / "out" / "song.flac"


def test_convert_args():
    a = convert.build_args("in.mkv", "out.mp4", convert.ConvertOptions(target="mp4", quality=720), True)
    assert "libx264" in a and "scale=-2:'min(720,ih)'" in a and a[-1] == "out.mp4"
    c = convert.build_args("in.mkv", "out.mp4", convert.ConvertOptions(target="mp4", copy_streams=True), True)
    assert c[c.index("-c") + 1] == "copy"
    m = convert.build_args("in.mp4", "out.mp3", convert.ConvertOptions(target="mp3", quality=192), True)
    assert "-vn" in m and m[m.index("-b:a") + 1] == "192k"
    with pytest.raises(ValueError):
        convert.build_args("in.mp3", "out.mp4", convert.ConvertOptions(target="mp4"), False)
