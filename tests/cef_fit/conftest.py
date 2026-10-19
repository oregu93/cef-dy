from pathlib import Path

import pytest
import yaml


REPOSITORY = Path(__file__).resolve().parents[2]
R7_BUNDLE = REPOSITORY / "04_Results/Stage03R/STAGE03R-CS15-PREDICTION-BUNDLE-MATERIALIZATION-001/PB-CS15-HIST-B2-R7.yaml"


@pytest.fixture(scope="session")
def r7_bundle():
    return yaml.safe_load(R7_BUNDLE.read_text(encoding="utf-8"))
