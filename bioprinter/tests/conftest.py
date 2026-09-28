import socket
import pytest
from bioprinter.config import demo_profile
from bioprinter.examples import make_inputs


@pytest.fixture(autouse=True)
def forbid_external_network(monkeypatch):
    original=socket.socket.connect
    def connect(sock,address):
        if isinstance(address,tuple) and address[0] not in {'127.0.0.1','::1','localhost'}:
            raise AssertionError('Tests may not contact a printer or external network')
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',connect)


@pytest.fixture
def profile():return demo_profile()


@pytest.fixture
def inputs(tmp_path):return make_inputs(tmp_path/'inputs')


@pytest.fixture(scope='session')
def demo_run(tmp_path_factory):
    from bioprinter.pipeline import compose
    root=tmp_path_factory.mktemp('full_demo')
    return compose(make_inputs(root/'inputs'),output_root=root/'runs')
