"""The deployment launcher is a sudo boundary, so `deploy.sh` refuses a helper whose protocol it
does not recognise. That check is only useful while the two numbers are kept in step: bumping the
helper alone makes `--install-helper` install a launcher that the very next deployment rejects,
with an error telling you to install it again."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _single(pattern: str, path: pathlib.Path) -> str:
    matches = re.findall(pattern, path.read_text(), flags=re.MULTILINE)
    assert len(matches) == 1, f"expected exactly one {pattern!r} in {path}, found {matches}"
    return matches[0]


def test_launcher_protocol_matches_what_the_deploy_script_expects():
    expected = _single(r"^helper_protocol=(\d+)$", ROOT / "deploy.sh")
    reported = _single(r"^PROTOCOL=(\d+)$", ROOT / "deploy" / "acervo" / "remote-helper.sh")
    assert expected == reported


def test_every_installer_flag_survives_the_launcher_allowlist():
    """The launcher passes through an explicit allowlist, so a flag added to `deploy.sh` and
    `install.sh` but not to it is refused at the boundary rather than reaching the installer."""
    helper = (ROOT / "deploy" / "acervo" / "remote-helper.sh").read_text()
    installer = (ROOT / "deploy" / "acervo" / "install.sh").read_text()
    forwarded = set(re.findall(r'installer_arguments \$?installer_arguments (--[a-z-]+)"?',
                               (ROOT / "deploy.sh").read_text()))
    forwarded |= {
        flag for flag in re.findall(r'set -- "\$@" (--[a-z-]+)$',
                                    (ROOT / "deploy.sh").read_text(), flags=re.MULTILINE)
    }
    assert forwarded, "expected deploy.sh to forward at least one installer flag"
    for flag in forwarded:
        assert f"{flag})" in helper, f"{flag} is not accepted by the passwordless launcher"
        assert f"{flag})" in installer, f"{flag} is not accepted by the installer"
