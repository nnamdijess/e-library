"""Cross-process data lease. One API worker, or one maintenance operation."""
from contextlib import contextmanager
import os
from pathlib import Path
import threading

_guard = threading.RLock()
_held = {}


class DataBusy(RuntimeError):
    pass


@contextmanager
def data_lease(directory: Path, purpose="maintenance"):
    directory = directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = str(directory)
    with _guard:
        previous = _held.get(key)
        if previous:
            # Multiple in-process ASGI clients may share the same server lease.
            if previous["purpose"] != purpose or (purpose != "server" and previous["thread"] != threading.get_ident()):
                raise DataBusy("Data is in use. Stop the backend before maintenance.")
            previous["count"] += 1
        else:
            path = directory / ".library.lock"
            if path.is_symlink():
                raise DataBusy("The data lock cannot be a symbolic link.")
            stream = path.open("a+b")
            try:
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b"0"); stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                stream.close()
                raise DataBusy("Data is in use. Stop the backend before maintenance; run only one API worker.") from error
            _held[key] = {"stream": stream, "purpose": purpose, "thread": threading.get_ident(), "count": 1}
    try:
        yield
    finally:
        with _guard:
            record = _held[key]
            record["count"] -= 1
            if record["count"] == 0:
                stream = record["stream"]
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                finally:
                    stream.close()
                    del _held[key]
