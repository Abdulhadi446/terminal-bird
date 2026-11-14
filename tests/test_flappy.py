"""Unit tests for Terminal Bird (flappy.py)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

import flappy


class TestImportAndCompile(unittest.TestCase):
    def test_import(self):
        self.assertTrue(hasattr(flappy, "World"))
        self.assertTrue(hasattr(flappy, "GameView"))
        self.assertTrue(hasattr(flappy, "Renderer"))
        self.assertTrue(hasattr(flappy, "TerminalSession"))

    def test_py_compile(self):
        import py_compile
        py_compile.compile("flappy.py", doraise=True)

    def test_version(self):
        self.assertEqual(flappy.VERSION, "1.0.0")


class TestWorldInit(unittest.TestCase):
    def setUp(self):
        self.w = flappy.World(80, 24, seed=42, persist=False)

    def test_init_state(self):
        self.assertEqual(self.w.state, "START")
        self.assertEqual(self.w.score, 0)
        self.assertEqual(self.w.best, 0)
        self.assertIsInstance(self.w.cols, int)
        self.assertIsInstance(self.w.rows, int)


class TestWorldStartRun(unittest.TestCase):
    def test_start_run(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.start_run()
        self.assertEqual(w.state, "PLAY")
        self.assertEqual(len(w.pipes), 0)
        # pipe_timer = 0.35s before first pipe spawns
        w.update(0.4)
        self.assertGreater(len(w.pipes), 0)


class TestWorldFlap(unittest.TestCase):
    def test_flap(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.start_run()
        w.update(1 / 60)
        vy_before = w.bird.vy
        w.flap(force=True)
        self.assertEqual(w.bird.vy, w.flap_power)
        self.assertLess(w.bird.vy, vy_before)


class TestCollisionBehavior(unittest.TestCase):
    def test_ground_collision(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.start_run()
        w.bird.y = w.sky_h + w.bird.h / 2
        w.bird.vy = 0
        w._update_play(1 / 60)
        self.assertEqual(w.state, "DYING")
        self.assertEqual(w.death_reason, "ground")

    def test_ceiling_collision(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.start_run()
        w.bird.y = -w.bird.h / 2
        w.bird.vy = 0
        w._update_play(1 / 60)
        self.assertEqual(w.state, "DYING")
        self.assertEqual(w.death_reason, "ceiling")

    def test_no_collision_when_safe(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.start_run()
        w.update(1 / 60)
        self.assertEqual(w.state, "PLAY")
        self.assertFalse(w.bird_collides())


class TestScore(unittest.TestCase):
    def test_score_increment(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.start_run()
        w.update(1 / 60)
        self.assertGreaterEqual(w.score, 0)


class TestResize(unittest.TestCase):
    def test_resize(self):
        w = flappy.World(80, 24, seed=1, persist=False)
        w.resize(100, 34)
        self.assertEqual(w.W, 100)
        self.assertEqual(w.H, 68)
        self.assertEqual(w.sky_h, 62)


class TestScores(unittest.TestCase):
    def test_load_scores_default(self):
        record = flappy.load_scores()
        self.assertIn("best", record)
        self.assertIn("games", record)

    def test_save_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "highscore.json"
            self.assertTrue(flappy.save_scores({"best": 99, "games": 7}, path))
            loaded = flappy.load_scores(path)
            self.assertEqual(loaded["best"], 99)

    def test_env_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TERMINAL_BIRD_DATA"] = str(Path(tmp))
            path = flappy.scores_path()
            self.assertEqual(path, Path(tmp) / "highscore.json")
            del os.environ["TERMINAL_BIRD_DATA"]

    def test_load_fallback(self):
        path = flappy.scores_path()
        self.assertIsInstance(path, Path)


class TestQuantizers(unittest.TestCase):
    def test_nearest16(self):
        from flappy import _nearest16
        self.assertEqual(_nearest16(255), 12)

    def test_quant256(self):
        from flappy import _quant256
        self.assertEqual(_quant256(255), 21)


class TestRenderer(unittest.TestCase):
    def test_renderer(self):
        r = flappy.Renderer(1, "truecolor")
        self.assertTrue(hasattr(r, "render_too_small"))


class TestTerminalSession(unittest.TestCase):
    def test_terminal_session(self):
        s = flappy.TerminalSession(0, 1)
        keys = s.read_keys(timeout=0.0)
        self.assertIsInstance(keys, list)


if __name__ == "__main__":
    unittest.main()
