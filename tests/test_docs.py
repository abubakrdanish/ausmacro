"""Run the examples in the public docstrings, against synthetic fixtures."""
from __future__ import annotations

import doctest
import warnings

import pytest

import ausmacro

# Each example that downloads gets one fixture, served in place of the real response.
EXAMPLES = {
    ausmacro.get: "SYNTHETIC_abs_cpi_monthly.csv",
    ausmacro.get_abs: "SYNTHETIC_abs_cpi_quarterly.csv",
    ausmacro.get_rba: "SYNTHETIC_rba_f1.csv",
    ausmacro.series: None,
    ausmacro.attribution: None,
    ausmacro.clear_cache: None,
}


@pytest.mark.parametrize("function", EXAMPLES, ids=lambda f: f.__name__)
def test_docstring_examples(function, fake_http):
    if EXAMPLES[function]:
        fake_http.reply(fixture=EXAMPLES[function])
    runner = doctest.DocTestRunner(optionflags=doctest.NORMALIZE_WHITESPACE)
    tests = doctest.DocTestFinder().find(function, function.__name__, globs={})
    assert sum(len(t.examples) for t in tests) >= 2
    with warnings.catch_warnings():
        # The get example asks for cities the fixture does not have.
        warnings.simplefilter("ignore")
        for test in tests:
            runner.run(test)
    assert runner.failures == 0
