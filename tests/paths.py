import os
from pathlib import Path

REPO_ROOT_DIR = Path(__file__).parent.parent.resolve()
PROJECT_DIR = REPO_ROOT_DIR / "tests"
TEST_SERVICES_DIR = Path(os.environ.get("TEST_SERVICES_DIR", REPO_ROOT_DIR / "test-services"))
