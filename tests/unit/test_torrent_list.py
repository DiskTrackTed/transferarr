import threading

from transferarr.models import TorrentList


class TestTorrentList:
    def test_append_and_iterate(self):
        torrents = TorrentList()

        torrents.append("a")
        torrents.append("b")

        assert list(torrents) == ["a", "b"]

    def test_discard_absent_is_noop(self):
        torrents = TorrentList(["a"])

        torrents.discard("missing")

        assert list(torrents) == ["a"]

    def test_snapshot_is_copy(self):
        torrents = TorrentList(["a"])

        snapshot = torrents.snapshot()
        snapshot.append("b")

        assert list(torrents) == ["a"]

    def test_getitem_returns_expected_item(self):
        torrents = TorrentList(["a", "b"])

        assert torrents[0] == "a"
        assert torrents[1] == "b"

    def test_concurrent_append_and_iterate(self):
        torrents = TorrentList(range(100))
        errors = []

        def append_items():
            for value in range(100, 200):
                torrents.append(value)

        def iterate_items():
            for _ in range(50):
                snapshot = list(torrents)
                if not snapshot:
                    errors.append("empty snapshot")

        threads = [
            threading.Thread(target=append_items),
            threading.Thread(target=iterate_items),
            threading.Thread(target=iterate_items),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert len(torrents) == 200