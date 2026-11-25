import pytest

from oryva.pipeline import build


@pytest.fixture(scope="session")
def tiny():
    return build("tiny", None, quiet=True)


@pytest.fixture(scope="session")
def tiny_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("tiny_export")
    build("tiny", d, quiet=True, command="pytest")
    return d
