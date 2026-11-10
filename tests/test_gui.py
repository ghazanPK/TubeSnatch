"""Offscreen GUI smoke tests: the window builds, tabs switch, rows behave."""

from tubesnatch import engine


def make_window(qapp):
    from tubesnatch.ui.main_window import MainWindow

    w = MainWindow()
    w.cfg.set("update_mode", "off")
    return w


def fake_result(n=3, kind="playlist"):
    entries = [engine.Entry(url=f"https://www.youtube.com/watch?v=id{i}", id=f"id{i}", title=f"Song {i}",
                            uploader="Artist", duration=180 + i, index=i + 1) for i in range(n)]
    return engine.ProbeResult(kind=kind, title="My Mix", uploader="Artist", thumbnail=None, entries=entries)


def test_window_and_tabs(qapp):
    w = make_window(qapp)
    for i in range(3):
        w.show_page(i)
        assert w.pages.currentIndex() == i
    from tubesnatch.ui.about import AboutDialog

    AboutDialog(w)
    w.quit_now()


def test_rows_formats_and_archive(qapp, tmp_path):
    w = make_window(qapp)
    tab = w.download
    tab.archive.clear()
    tab.archive.add("youtube id1")
    tab.chk_skip.setChecked(True)
    tab._probe_done(fake_result())
    assert len(tab.rows) == 3
    assert tab.rows[1].state == "archived" and not tab._is_checked(1) and tab._is_checked(0)

    # switch a row to FLAC → quality is "Lossless"
    from tubesnatch.ui.download_tab import C_FMT, C_QUAL
    from tubesnatch.ui.widgets import select_data

    select_data(tab._cell(0, C_FMT), "flac")
    assert tab.rows[0].fmt == "flac" and tab._cell(0, C_QUAL).currentText() == "Lossless"
    select_data(tab._cell(0, C_FMT), "mp4")
    assert tab.rows[0].quality in engine.VIDEO_HEIGHTS + [0]

    # job options honour playlist folder + numbering and per-row trim
    tab.dest_input.setText(str(tmp_path))
    tab.rows[2].trim = (10, 20)
    o = tab._job_options(tab.rows[2])
    assert o.outdir.endswith("My Mix") and o.filename_prefix == "003 - " and o.trim == (10, 20)

    # apply defaults to checked rows
    tab.mode_audio.setChecked(True)
    tab._mode_changed()
    select_data(tab.fmt_combo, "opus")
    tab._apply_defaults_to_checked()
    checked = [r for i, r in enumerate(tab.rows) if tab._is_checked(i)]
    assert checked and all(r.fmt == "opus" for r in checked)

    # re-fetching the same playlist doesn't duplicate rows
    tab._probe_done(fake_result())
    assert len(tab.rows) == 3
    tab.archive.clear()
    w.quit_now()


def test_convert_tab_adds_files(qapp, tmp_path):
    w = make_window(qapp)
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"0")
    (tmp_path / "notes.txt").write_text("x")
    assert w.convert.add_files([str(tmp_path)]) == 1  # folders: media files only
    assert w.convert.add_files([str(f)]) == 0  # no duplicates
    w.quit_now()
