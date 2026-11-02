"""Gesture classification, smoothing and hold-to-confirm."""
import unittest

from gesture_slice.gesture_detection import Gesture, GestureDetector, OneEuroFilter
from gesture_slice.hand_tracking import HandSample


def hand(extended=(True, True, True, True), thumb_out=True, offset=(0.5, 0.5)):
    """Synthetic 21-landmark hand (wrist at the bottom, fingers pointing up)."""
    ox, oy = offset
    pts = [(0.0, 0.0)] * 21
    pts[0] = (0.0, 0.0)                       # wrist
    mcp_x = (-0.06, -0.02, 0.02, 0.06)
    for f, x in enumerate(mcp_x):
        mcp, pip, dip, tip = 5 + 4 * f, 6 + 4 * f, 7 + 4 * f, 8 + 4 * f
        pts[mcp] = (x, -0.10)
        pts[pip] = (x, -0.15)
        if extended[f]:
            pts[dip], pts[tip] = (x, -0.19), (x, -0.23)
        else:                                 # curled back towards the palm
            pts[dip], pts[tip] = (x, -0.12), (x, -0.08)
    pts[1], pts[2], pts[3] = (-0.05, -0.03), (-0.08, -0.05), (-0.10, -0.07)
    pts[4] = (-0.14, -0.09) if thumb_out else (-0.05, -0.09)
    return tuple((x + ox, y + oy) for x, y in pts)


class ClassifyTests(unittest.TestCase):
    def test_open_palm(self):
        self.assertEqual(GestureDetector.classify(hand()), Gesture.OPEN_PALM)

    def test_fist(self):
        self.assertEqual(GestureDetector.classify(hand((False,) * 4, thumb_out=False)), Gesture.FIST)

    def test_point(self):
        self.assertEqual(GestureDetector.classify(hand((True, False, False, False))), Gesture.POINT)

    def test_missing_hand(self):
        self.assertEqual(GestureDetector.classify(None), Gesture.NONE)


class DetectorTests(unittest.TestCase):
    def feed(self, det, landmarks, seconds, start=0.0, fps=30):
        frames = []
        for i in range(int(seconds * fps)):
            frames.append(det.update(HandSample(start + i / fps, landmarks)))
        return frames

    def test_palm_must_be_held_before_pause(self):
        det = GestureDetector()
        frames = self.feed(det, hand(), 0.4)
        self.assertFalse(any(f.event for f in frames))       # too short
        frames = self.feed(det, hand(), 0.6, start=0.4)
        events = [f.event for f in frames if f.event]
        self.assertEqual(events, ["pause"])                   # fires exactly once

    def test_fist_resumes(self):
        det = GestureDetector()
        frames = self.feed(det, hand((False,) * 4, thumb_out=False), 1.2)
        self.assertEqual([f.event for f in frames if f.event], ["resume"])

    def test_fast_swipe_creates_segment_with_speed(self):
        det = GestureDetector()
        det.update(HandSample(0.0, hand((True, False, False, False), offset=(0.3, 0.5))))
        frame = det.update(HandSample(1 / 30, hand((True, False, False, False), offset=(0.6, 0.5))))
        self.assertIsNotNone(frame.segment)
        self.assertGreater(frame.segment[4], 1000)

    def test_hand_lost_resets_motion(self):
        det = GestureDetector()
        det.update(HandSample(0.0, hand(offset=(0.2, 0.5))))
        det.update(HandSample(0.03, None))
        frame = det.update(HandSample(0.06, hand(offset=(0.8, 0.5))))
        self.assertIsNone(frame.segment)                      # no giant jump-cut

    def test_mapping_is_clamped_to_canvas(self):
        det = GestureDetector(1000, 500)
        self.assertEqual(det.map_to_canvas(-1, -1), (0, 0))
        self.assertEqual(det.map_to_canvas(2, 2), (1000, 500))

    def test_one_euro_reduces_jitter(self):
        f = OneEuroFilter()
        values = [f(100 + (3 if i % 2 else -3), i / 30) for i in range(60)]
        spread = max(values[30:]) - min(values[30:])
        self.assertLess(spread, 3)


if __name__ == "__main__":
    unittest.main()
