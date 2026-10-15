"""Test-only phase observations; application output and stack evidence are separate."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import textwrap
from threading import Thread
from time import monotonic, time_ns


def clock_snapshot():
    active = None
    if sys.platform == "win32":
        import ctypes
        value = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)):
            raise ctypes.WinError()
        active = value.value
    return {"wall_ns": time_ns(), "unbiased_100ns": active, "pid": os.getpid()}


def instrument_stalled_composition(source, directory):
    """Observe real imports, composition, handler.write and interpreter atexit."""
    prelude = '''
import os, sys, time, json
def mark(phase):
    active = None
    if sys.platform == "win32":
        import ctypes
        value = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)):
            raise ctypes.WinError()
        active = value.value
    print(json.dumps(dict(phase=phase, wall_ns=time.time_ns(),
                          unbiased_100ns=active, pid=os.getpid())), flush=True)
mark("interpreter_entered")
import atexit, faulthandler
from threading import Event, Thread
trace = open(TRACE_PATH, "w")
faulthandler.enable(file=trace, all_threads=True)
faulthandler.dump_traceback_later(4.5, repeat=True, file=trace)
go = Event()
def control():
    for command in sys.stdin:
        if command == "GO\\n":
            go.set()
        elif command == "DUMP\\n":
            faulthandler.dump_traceback(file=trace, all_threads=True)
            mark("timeout_stack_dumped")
Thread(target=control, daemon=True, name="probe-control").start()
atexit.register(lambda: mark("atexit"))
'''.replace("TRACE_PATH", repr(str(Path(directory) / "child-stack.txt")))
    source = textwrap.dedent(source)
    for old, new in (
        ("entered = Event()", 'mark("imports_done")\nentered = Event()'),
        ('print("write_entered", flush=True)', 'mark("write_entered")'),
        ("def fail(startup):", 'mark("logger_config_ready")\ndef fail(startup):'),
        ("module.create_app(startup=startup)", '''mark("ready")
assert go.wait(5), "parent trigger missing"
faulthandler.cancel_dump_traceback_later()
faulthandler.dump_traceback_later(4.5, repeat=True, file=trace)
mark("before_composition_failure")
try:
    module.create_app(startup=startup)
except SystemExit as failure:
    mark("system_exit_returned")
    assert failure.code == 1
    mark("before_atexit")
    raise
'''),
    ):
        assert source.count(old) == 1
        source = source.replace(old, new)
    return textwrap.dedent(prelude) + source


def run_triggered_child(source, directory):
    """Separate setup watchdog from an unchanged 5s deadline starting before GO."""
    directory = Path(directory)
    events, lines, errors, markers = [], [], [], queue.Queue()

    def record(phase, **details):
        events.append({"phase": phase, **clock_snapshot(), **details})
        (directory / "parent-phases.json").write_text(json.dumps(events, indent=2))

    record("before_spawn")
    child = subprocess.Popen([sys.executable, "-u", "-B", "-X", "utf8", "-c", source],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    record("spawn_returned", popen_pid=child.pid)
    deadline, triggered, failure = monotonic() + 5, False, None

    def read_markers():
        for line in child.stdout:
            lines.append(line)
            markers.put((line, clock_snapshot()))
        markers.put((None, clock_snapshot()))

    def read_errors():
        errors.append(child.stderr.read())

    readers = [Thread(target=read_markers), Thread(target=read_errors)]
    for thread in readers:
        thread.start()
    try:
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise queue.Empty
            line, received = markers.get(timeout=remaining)
            if line is None:
                child.wait(timeout=max(0, deadline - monotonic()))
                break
            marker = json.loads(line)
            record("marker_received", child=marker, received_at=received)
            if marker["phase"] == "ready":
                assert not triggered
                record("trigger_before_write")
                deadline = monotonic() + 5
                child.stdin.write(b"GO\n")
                child.stdin.flush()
                triggered = True
                record("trigger_written")
        record("exit_observed", returncode=child.returncode)
    except (queue.Empty, subprocess.TimeoutExpired):
        failure = "product_exit_5s" if triggered else "setup_import_watchdog_5s"
        record("timeout", reason=failure, poll=child.poll())
        if child.poll() is None:
            try:
                child.stdin.write(b"DUMP\n")
                child.stdin.flush()
                # Observation after failure cannot convert the deadline to PASS.
                while True:
                    line, received = markers.get(timeout=1)
                    if line is None:
                        break
                    marker = json.loads(line)
                    record("timeout_marker_received", child=marker, received_at=received)
                    if marker["phase"] == "timeout_stack_dumped":
                        break
            except (OSError, queue.Empty):
                record("timeout_stack_unavailable")
        if sys.platform == "win32":
            observation = subprocess.run([
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|pytest' } | "
                "Select-Object ProcessId,ParentProcessId,Name,CreationDate,KernelModeTime,UserModeTime,ThreadCount | ConvertTo-Json"
            ], capture_output=True, timeout=15)
            (directory / "timeout-processes.json").write_bytes(observation.stdout)
    finally:
        if child.poll() is None:
            if sys.platform == "win32":
                # A venv launcher can own a second interpreter PID. Reap only
                # this newly spawned tree, including that owned interpreter.
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               capture_output=True, timeout=10)
            else:
                child.kill()
        child.wait(timeout=5)
        for thread in readers:
            thread.join(timeout=5)
            assert not thread.is_alive(), "owned pipe reader remains"
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()
        (directory / "child-stdout.txt").write_bytes(b"".join(lines))
        (directory / "child-stderr.txt").write_bytes(b"".join(errors))
    assert failure is None, f"{failure}; phase/stack evidence: {directory}"
    return child.returncode, b"".join(lines), b"".join(errors)
