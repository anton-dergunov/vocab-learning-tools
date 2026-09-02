"""The compiler's command line, especially the batch build.

`build --all` downloads about 11.6 GiB across 46 rows, so the two things worth pinning are which
rows an invocation actually selects and what happens when one of them fails ten gigabytes in.
"""

from __future__ import annotations

import pytest

from vocabgen.dictionaries import cli
from vocabgen.dictionaries.build import BuildResult
from vocabgen.dictionaries.catalogue import find, load_catalogue
from vocabgen.dictionaries.container import BuildReport


def selected(*argv: str) -> list[str]:
    return cli._selected(cli.build_parser().parse_args(["build", *argv]))


def test_a_single_id_selects_only_that_row():
    assert selected("--id", "cc-cedict") == ["cc-cedict"]


def test_all_selects_every_offline_row_and_no_others():
    every = selected("--all")
    offline = [row.id for row in load_catalogue() if row.kind == "offline"]
    assert every == offline
    # Online sources are answered by a route and link-outs are an address; neither compiles.
    assert not {row.id for row in load_catalogue() if row.kind != "offline"} & set(every)


def test_a_language_filter_matches_the_primary_subtag():
    """`zh` has to cover zh-Hans and zh-Hant, or the Chinese dictionaries split across two names."""
    chinese = selected("--all", "--language", "zh")
    assert "cc-cedict" in chinese          # zh-Hans
    assert "moedict-zh" in chinese         # zh-Hant
    assert "kaikki-zh-zh" in chinese       # zh
    assert "cc-cedict" not in selected("--all", "--language", "es")


def test_several_languages_can_be_asked_for_at_once():
    both = selected("--all", "--language", "es,zh")
    assert set(selected("--all", "--language", "es")) <= set(both)
    assert set(selected("--all", "--language", "zh")) <= set(both)


def test_an_unknown_language_selects_nothing_rather_than_everything():
    assert selected("--all", "--language", "xx") == []


def test_id_and_all_cannot_both_be_given():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["build", "--id", "cc-cedict", "--all"])


def test_a_batch_keeps_going_when_one_row_fails(monkeypatch, capsys, tmp_path):
    """One source moving must not abandon the gigabytes already downloaded behind it."""
    attempted: list[str] = []

    def build(identifier, **_kwargs):
        attempted.append(identifier)
        if identifier == "cc-cedict":
            raise RuntimeError("the source moved")
        return BuildResult(row=find(identifier), report=BuildReport(), destination=tmp_path, seconds=0.1)

    monkeypatch.setattr(cli.builder, "build", build)
    status = cli.main(["build", "--all", "--language", "zh", "--out", str(tmp_path)])

    assert len(attempted) > 1, "the batch stopped at the failure instead of carrying on"
    assert "cc-cedict" in attempted
    assert status == 1, "a batch with a failure in it must not report success"
    output = capsys.readouterr()
    assert "the source moved" in output.err
    assert "1 of" in output.err and "did not build" in output.err


def test_a_batch_that_works_reports_success(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.builder, "build", lambda identifier, **_: BuildResult(
        row=find(identifier), report=BuildReport(), destination=tmp_path, seconds=0.1))
    assert cli.main(["build", "--all", "--language", "yue", "--out", str(tmp_path)]) == 0


def test_listing_the_catalogue_names_every_row(capsys):
    assert cli.main(["list"]) == 0
    printed = capsys.readouterr().out
    for row in load_catalogue():
        assert row.id in printed
