"""SQLite layer: sessions, high scores, statistics, leaderboard, settings."""
import os
import tempfile
import unittest

from gesture_slice.database import DatabaseManager
from gesture_slice.game_engine import GameStats


def stats(score, sliced=10, missed=2, combo=3):
    return GameStats(score=score, fruits_sliced=sliced, fruits_missed=missed, fruits_spawned=sliced + missed,
                     bombs_hit=1, max_combo=combo, level=2, elapsed=60.0)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_record_and_high_score(self):
        r1 = self.db.record_session("Asha", stats(120), "Gesture")
        self.assertTrue(r1["saved"] and r1["new_record"])
        r2 = self.db.record_session("Asha", stats(80), "Gesture")
        self.assertFalse(r2["new_record"])
        self.assertEqual(self.db.get_player_best("Asha"), 120)
        r3 = self.db.record_session("asha", stats(300), "Mouse")     # names are case-insensitive
        self.assertTrue(r3["new_record"])
        self.assertEqual(self.db.get_player_best("Asha"), 300)

    def test_statistics_accumulate(self):
        self.db.record_session("Ravi", stats(100, sliced=5, combo=2), "Gesture")
        self.db.record_session("Ravi", stats(50, sliced=7, combo=4), "Gesture")
        s = self.db.get_player_stats("Ravi")
        self.assertEqual(s["games_played"], 2)
        self.assertEqual(s["total_fruits_sliced"], 12)
        self.assertEqual(s["best_combo"], 4)
        self.assertEqual(s["total_score"], 150)

    def test_leaderboard_order(self):
        self.db.record_session("A", stats(100), "Gesture")
        self.db.record_session("B", stats(300), "Gesture")
        self.db.record_session("C", stats(200), "Gesture")
        board = self.db.get_leaderboard()
        self.assertEqual([r["name"] for r in board], ["B", "C", "A"])
        self.assertEqual([r["rank"] for r in board], [1, 2, 3])
        self.assertEqual(self.db.get_global_best(), 300)

    def test_settings_roundtrip(self):
        self.db.save_setting("sound", "Off")
        self.assertEqual(self.db.load_settings()["sound"], "Off")

    def test_unwritable_path_falls_back_to_memory(self):
        db = DatabaseManager("/proc/definitely/not/writable/x.db" if os.name != "nt" else "Z:\\nope\\x.db")
        try:
            self.assertIsNotNone(db.error)
            self.assertTrue(db.record_session("X", stats(10), "Mouse")["saved"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
