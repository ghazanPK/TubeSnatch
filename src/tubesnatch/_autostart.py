"""Start the GUI when the portable runtime is launched as ``TubeSnatch.exe``.

The portable Windows build ships Python's own, PSF-signed ``pythonw.exe`` renamed to
``TubeSnatch.exe``, so it runs on PCs with Smart App Control (which blocks unsigned .exe files and
web-downloaded .cmd/.lnk launchers). A one-line ``.pth`` file imports this module during interpreter
startup. When the executable is TubeSnatch.exe and it wasn't asked to run Python code (no ``-m``/``-c``/
script), we run the app and hard-exit.
"""

import os
import sys
from pathlib import Path


def _wants_app() -> bool:
    if Path(sys.executable).stem.lower() != "tubesnatch":
        return False
    argv = list(getattr(sys, "orig_argv", sys.argv))[1:]
    # plain double-click, or links dropped onto the exe (Python options like -m/-c run Python normally)
    return all(a.startswith(("http://", "https://")) for a in argv)


if _wants_app():
    argv = list(getattr(sys, "orig_argv", sys.argv))
    sys.argv = [argv[0], *argv[1:]]
    try:
        from tubesnatch import main

        code = main(exit_process=False)
    except BaseException:  # noqa: BLE001 - last-resort crash log for a windowless process
        import traceback

        log = Path(os.environ.get("TEMP", ".")) / "tubesnatch-crash.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        code = 1
    os._exit(code or 0)  # don't fall through into the (windowless) interactive interpreter
