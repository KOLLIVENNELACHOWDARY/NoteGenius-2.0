import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = open(os.path.join(HERE, "sample_physics.txt"), encoding="utf-8").read()
MATHS = open(os.path.join(HERE, "sample_maths.txt"), encoding="utf-8").read()


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "test-key"})


@pytest.fixture()
def client(app):
    return app.test_client()


def token(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)


@pytest.fixture()
def loaded(client):
    """A client that already has the sample notes loaded."""
    resp = client.post("/text_input", data={"input_text": SAMPLE, "csrf_token": token(client)})
    assert resp.status_code == 302
    return client


@pytest.fixture()
def sample():
    return SAMPLE
