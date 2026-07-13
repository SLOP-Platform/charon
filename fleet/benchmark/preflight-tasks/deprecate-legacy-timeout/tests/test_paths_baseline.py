from gateway.proxy import send
from gateway.settings import get_config


def test_primary_path_honors_config():
    assert send({"id": 1})["timeout"] == get_config().timeout
