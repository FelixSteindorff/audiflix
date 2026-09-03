"""Console entry point for the packaged diagnostic (``audiflix-selftest.exe``).

The main executable is a windowed application and therefore has nowhere to
print to. This second, console-mode executable runs exactly the same checks and
is what CI and support requests use:

    audiflix-selftest.exe

It exits with 0 when the bundled audio engine works on this machine.
"""

from audiflix.logging_setup import setup_logging
from audiflix.selftest import run_selftest

if __name__ == "__main__":
    setup_logging(console=True)
    raise SystemExit(run_selftest())
