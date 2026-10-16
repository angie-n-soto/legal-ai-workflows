from pathlib import Path

import pytest

from legal_workflows.cms import MockCMSClient

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "mock_cms" / "claims"
SAMPLE_INPUTS = ROOT / "sample_inputs"


@pytest.fixture
def client():
    return MockCMSClient(DATA)
