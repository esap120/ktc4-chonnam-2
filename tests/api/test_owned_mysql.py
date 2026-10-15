"""TCP cleanup probe behavior, using native sockets without a MySQL substitute."""
from types import SimpleNamespace
import socket

import pytest
import owned_mysql


def test_closed_port_probe_avoids_native_tcp_self_connect(monkeypatch):
    real_socket = socket.socket
    with real_socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    pairs = []
    candidates = []
    class CandidateSocket(real_socket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.bound = False
        def bind(self, address):
            # Exercise the valid ephemeral candidate equal to the destination.
            if not candidates:
                address = ("127.0.0.1", port)
            super().bind(address)
            self.bound = True
            candidates.append(self.getsockname()[1])
        def connect_ex(self, address):
            if not self.bound:
                self.bind(address)
            result = super().connect_ex(address)
            pairs.append((self.getsockname()[1], address[1]))
            return result
    monkeypatch.setattr(owned_mysql, "socket", SimpleNamespace(socket=CandidateSocket))
    owned_mysql.assert_port_closed(port)
    assert pairs and all(local != remote for local, remote in pairs)


def test_closed_port_probe_rejects_real_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with pytest.raises(AssertionError, match="port remains open"):
            owned_mysql.assert_port_closed(listener.getsockname()[1])
