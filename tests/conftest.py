from pathlib import Path


def pytest_configure(config):
    # Use the repository's ignored scratch area; Windows user temp ACLs may differ.
    (Path(__file__).resolve().parents[1] / "tmp").mkdir(exist_ok=True)

