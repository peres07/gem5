# Copyright (c) 2026 The Project 12 contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Register the Project 12 tests with the standard gem5 runner."""

import unittest
from pathlib import Path


def load_tests(loader, standard_tests, pattern):
    configs = Path(__file__).resolve().parents[2] / "configs/projetos/p12"
    standard_tests.addTests(
        unittest.TestLoader().discover(str(configs), pattern="test_*p12.py",
                        top_level_dir=str(configs))
    )
    return standard_tests
