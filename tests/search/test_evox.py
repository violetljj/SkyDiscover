"""Tests for EvoX search config and utilities."""

from pathlib import Path

import skydiscover.search.route  # noqa: F401,E402
from skydiscover.config import Config, SearchConfig
from skydiscover.search.registry import setup_search


class TestSwitchIntervalConfig:
    def test_default_none(self):
        assert SearchConfig().switch_interval is None

    def test_from_yaml_dict(self):
        config = Config.from_dict({"search": {"type": "evox", "switch_interval": 5}})
        assert config.search.switch_interval == 5

    def test_omitted_stays_none(self):
        config = Config.from_dict({"search": {"type": "evox"}})
        assert config.search.switch_interval is None


class TestRepoRootResolution:
    """Verify variation_operator_generator.py uses the correct parents[] index."""

    def _vog_path(self):
        return (
            Path(__file__).resolve().parent.parent.parent
            / "skydiscover"
            / "search"
            / "evox"
            / "utils"
            / "variation_operator_generator.py"
        )

    def test_parents4_is_repo_root(self):
        assert (self._vog_path().parents[4] / "pyproject.toml").exists()

    def test_parents3_is_not_repo_root(self):
        assert not (self._vog_path().parents[3] / "pyproject.toml").exists()


def test_setup_search_reads_builtin_strategy_as_utf8(tmp_path):
    initial = tmp_path / "initial_strategy.py"
    initial.write_text("# curly quote: \u201cstrategy\u201d\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[2]

    _, solution = setup_search(
        initial_program_path=str(initial),
        evaluation_file=str(
            root / "skydiscover" / "search" / "evox" / "database" / "search_strategy_evaluator.py"
        ),
        config_path=str(root / "skydiscover" / "search" / "evox" / "config" / "search.yaml"),
        output_dir=str(tmp_path / "outputs"),
    )

    assert solution == "# curly quote: \u201cstrategy\u201d\n"
