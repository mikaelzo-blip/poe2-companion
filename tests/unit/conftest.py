"""Shared evaluation fixtures for unit tests."""

import pytest

from tests.unit.eval_helpers import Failing, Flat, Ring2Empty, Stub


@pytest.fixture
def positive_pob_stub():
    return Stub()


@pytest.fixture
def flat_pob_stub():
    return Flat()


@pytest.fixture
def failing_pob_stub():
    return Failing()


@pytest.fixture
def ring2_empty_stub():
    return Ring2Empty()
