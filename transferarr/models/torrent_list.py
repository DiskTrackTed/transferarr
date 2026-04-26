import threading
from contextlib import contextmanager


class TorrentList:
    def __init__(self, items=None):
        self._list = list(items or [])
        self._lock = threading.RLock()

    def __iter__(self):
        with self._lock:
            return iter(list(self._list))

    def __len__(self):
        with self._lock:
            return len(self._list)

    def __contains__(self, item):
        with self._lock:
            return item in self._list

    def __getitem__(self, index):
        with self._lock:
            return self._list[index]

    def append(self, item):
        with self._lock:
            self._list.append(item)

    def remove(self, item):
        with self._lock:
            self._list.remove(item)

    def discard(self, item):
        with self._lock:
            try:
                self._list.remove(item)
            except ValueError:
                pass

    def snapshot(self):
        with self._lock:
            return list(self._list)

    def replace(self, items):
        with self._lock:
            self._list = list(items)

    @contextmanager
    def locked(self):
        with self._lock:
            yield self._list