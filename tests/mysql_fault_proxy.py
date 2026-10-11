"""Local test-only MySQL packet relay that consumes a real COMMIT OK packet.

TLS must be disabled by the test client. This is deliberately not a general
MySQL proxy: each client uses the ordinary sequential command protocol.
"""

import socket
import threading


class CommitResponseProxy:
    def __init__(self, host, port, *, drop_commits=1):
        self.upstream = (host, port)
        self.remaining = drop_commits
        self.commit_forwarded = 0
        self.commit_ok_dropped = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sockets = []
        self._threads = []
        self._errors = []
        self._armed = False

    def arm(self):
        # SQLAlchemy/PyMySQL may issue initialization COMMITs. Fault only the
        # transaction whose callback has actually started, never a handshake.
        self._armed = True

    def __enter__(self):
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen()
        self._listener.settimeout(0.2)
        self.port = self._listener.getsockname()[1]
        self._start(self._accept)
        return self

    def _start(self, target, *args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        self._threads.append(thread)
        thread.start()

    @staticmethod
    def _close(sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    def _accept(self):
        while not self._stop.is_set():
            try:
                client, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                server = socket.create_connection(self.upstream, timeout=5)
            except OSError as error:
                self._errors.append(error)
                self._close(client)
                continue
            for sock in (client, server):
                sock.settimeout(0.2)
            self._sockets.extend((client, server))
            ended, committing = threading.Event(), threading.Event()
            self._start(self._relay, client, server, ended, committing, False)
            self._start(self._relay, server, client, ended, committing, True)

    def _receive(self, source, size, ended):
        data = bytearray()
        while len(data) < size and not ended.is_set() and not self._stop.is_set():
            try:
                chunk = source.recv(size - len(data))
            except socket.timeout:
                continue
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data) if len(data) == size else None

    def _relay(self, source, destination, ended, committing, from_server):
        try:
            while not ended.is_set() and not self._stop.is_set():
                header = self._receive(source, 4, ended)
                if header is None:
                    break
                payload = self._receive(source, int.from_bytes(header[:3], "little"), ended)
                if payload is None:
                    break
                if (not from_server and self._armed and payload[:1] == b"\x03"
                        and payload[1:].strip().upper() == b"COMMIT"):
                    with self._lock:
                        self.commit_forwarded += 1
                    committing.set()
                elif from_server and committing.is_set():
                    committing.clear()
                    if payload[:1] == b"\x00":
                        with self._lock:
                            drop = self.remaining > 0
                            if drop:
                                self.remaining -= 1
                                self.commit_ok_dropped += 1
                        if drop:
                            break
                destination.sendall(header + payload)
        except OSError:
            # EOF/reset is the intentional fault, also used by KILL tests.
            pass
        finally:
            ended.set()
            self._close(source)
            self._close(destination)

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        self._close(self._listener)
        for sock in self._sockets:
            self._close(sock)
        for thread in self._threads:
            thread.join(timeout=5)
        if exc_type is None:
            assert not self._errors, "proxy upstream connection failed"
            assert not any(thread.is_alive() for thread in self._threads), "proxy thread did not stop"
