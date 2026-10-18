"""Tests for quests.py – QuestTracker logic with a fake clock and fake processes."""
from pathlib import Path

from orbifier.quests import (
    QuestTracker, format_mmss, RUNNING, DONE, STOPPED,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeProc:
    def __init__(self):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 1

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def make_tracker(duration=900):
    clock = FakeClock()
    return QuestTracker(duration, clock=clock), clock


class TestFormatMmss:
    def test_full(self):
        assert format_mmss(900) == "15:00"

    def test_rounds_up_partial_seconds(self):
        assert format_mmss(59.2) == "01:00"

    def test_zero_and_negative(self):
        assert format_mmss(0) == "00:00"
        assert format_mmss(-5) == "00:00"


class TestQuestTracker:
    def test_remaining_counts_down(self):
        tracker, clock = make_tracker()
        q = tracker.add("Game.exe", FakeProc())
        assert tracker.remaining(q) == 900
        clock.now += 61
        assert tracker.remaining(q) == 839
        assert format_mmss(tracker.remaining(q)) == "13:59"

    def test_fraction_left(self):
        tracker, clock = make_tracker(100)
        q = tracker.add("Game.exe", FakeProc())
        assert tracker.fraction_left(q) == 1.0
        clock.now += 25
        assert tracker.fraction_left(q) == 0.75
        clock.now += 500
        assert tracker.fraction_left(q) == 0.0

    def test_status_running_then_done(self):
        tracker, clock = make_tracker(60)
        q = tracker.add("Game.exe", FakeProc())
        assert tracker.status(q) == RUNNING
        clock.now += 60
        assert tracker.status(q) == DONE
        assert tracker.remaining(q) == 0

    def test_status_stopped_when_process_exits(self):
        tracker, _clock = make_tracker()
        proc = FakeProc()
        q = tracker.add("Game.exe", proc)
        proc.returncode = 0
        assert tracker.status(q) == STOPPED

    def test_stop_terminates_removes_and_deletes_exe(self, tmp_path):
        tracker, _clock = make_tracker()
        exe = tmp_path / "Game.exe"
        exe.write_bytes(b"x")
        proc = FakeProc()
        q = tracker.add("Game.exe", proc, exe)
        tracker.stop(q)
        assert proc.terminated
        assert tracker.quests == []
        assert not exe.exists()

    def test_stop_keeps_exe_shared_with_live_quest(self, tmp_path):
        tracker, _clock = make_tracker()
        exe = tmp_path / "Game.exe"
        exe.write_bytes(b"x")
        q1 = tracker.add("Game.exe", FakeProc(), exe)
        tracker.add("Game.exe", FakeProc(), exe)
        tracker.stop(q1)
        assert exe.exists()
        assert len(tracker.quests) == 1

    def test_stop_all(self):
        tracker, _clock = make_tracker()
        procs = [FakeProc(), FakeProc()]
        for i, p in enumerate(procs):
            tracker.add(f"Game{i}.exe", p)
        tracker.stop_all()
        assert tracker.quests == []
        assert all(p.terminated for p in procs)

    def test_ids_are_unique_and_get_works(self):
        tracker, _clock = make_tracker()
        a = tracker.add("A.exe", FakeProc())
        b = tracker.add("B.exe", FakeProc())
        assert a.qid != b.qid
        assert tracker.get(b.qid) is b
        assert tracker.get(999) is None

    def test_custom_duration(self):
        tracker, clock = make_tracker(900)
        q = tracker.add("Custom.exe", FakeProc(), duration_s=300)
        assert tracker.remaining(q) == 300
        clock.now += 100
        assert tracker.remaining(q) == 200

    def test_stop_cleans_empty_parent_directories(self, tmp_path):
        tracker, _clock = make_tracker()
        sub = tmp_path / "Win64" / "nested"
        sub.mkdir(parents=True)
        exe = sub / "Game.exe"
        exe.write_bytes(b"x")
        proc = FakeProc()
        q = tracker.add("Game.exe", proc, exe)
        tracker.stop(q)
        assert not exe.exists()
        assert not sub.exists()

    def test_stop_preserves_selected_output_directory(self, tmp_path):
        tracker, _clock = make_tracker()
        output = tmp_path / "chosen"
        exe = output / "Bin/game.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"placeholder")
        quest = tracker.add("Game", FakeProc(), exe, cleanup_root=output)
        tracker.stop(quest)
        assert output.is_dir()
        assert not exe.parent.exists()

    def test_cleanup_preserves_unowned_helper_files(self, tmp_path):
        tracker, _clock = make_tracker()
        exe = tmp_path / "game.exe"
        exe.write_bytes(b"placeholder")
        config = tmp_path / "pyvenv.cfg"
        config.write_text("existing environment")
        quest = tracker.add("Game", FakeProc(), exe, cleanup_root=tmp_path)
        tracker.stop(quest)
        assert config.read_text() == "existing environment"

    def test_owned_helpers_are_removed_after_last_quest_in_folder(self, tmp_path):
        tracker, _clock = make_tracker()
        helper = tmp_path / "_orbifier_timer.pyw"
        helper.write_text("owned helper")
        a, b = tmp_path / "a.exe", tmp_path / "b.exe"
        a.write_bytes(b"placeholder")
        b.write_bytes(b"placeholder")
        first = tracker.add("A", FakeProc(), a, cleanup_root=tmp_path,
                            cleanup_files=(helper,))
        second = tracker.add("B", FakeProc(), b, cleanup_root=tmp_path,
                             cleanup_files=(helper,))
        tracker.stop(first)
        assert helper.exists()
        tracker.stop(second)
        assert not helper.exists()
        assert tmp_path.exists()

    def test_tilde_output_folder_is_preserved(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        output = tmp_path / "selected"
        output.mkdir()
        exe = output / "game.exe"
        exe.write_bytes(b"placeholder")
        tracker, _clock = make_tracker()
        quest = tracker.add("Game", FakeProc(), exe, cleanup_root=Path("~/selected"))
        tracker.stop(quest)
        assert output.is_dir()
