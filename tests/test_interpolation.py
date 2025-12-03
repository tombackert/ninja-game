import unittest
from dataclasses import dataclass
from scripts.network.interpolation import SnapshotBuffer, interpolate_entity


@dataclass
class MockState:
    pos: list
    velocity: list
    flip: bool
    action: str


class TestInterpolation(unittest.TestCase):
    def test_buffer_push_and_retrieval(self):
        buf = SnapshotBuffer(max_size=5)
        buf.push(100, "state_100")
        buf.push(110, "state_110")

        # Test Exact Match
        prev, nxt, t = buf.get_surrounding_snapshots(100)
        self.assertEqual(prev[0], 100)  # Actually, if target == prev, it returns prev, next, 0.0?
        # My logic: if prev_tick <= target_tick < curr_tick
        # If target == 100 (oldest), it falls into "older than oldest"? No, 100 is index 0.
        # Wait, loop goes range(len-1, 0, -1). indices: 1.
        # prev=0, curr=1. 100 <= 100 < 110. YES.
        self.assertEqual(prev[1], "state_100")
        self.assertEqual(nxt[1], "state_110")
        self.assertEqual(t, 0.0)

        # Test Middle
        prev, nxt, t = buf.get_surrounding_snapshots(105)
        self.assertEqual(prev[1], "state_100")
        self.assertEqual(nxt[1], "state_110")
        self.assertEqual(t, 0.5)

        # Test newer (lag)
        prev, nxt, t = buf.get_surrounding_snapshots(120)
        self.assertEqual(prev[0], 110)
        self.assertIsNone(nxt)

        # Test older (history lost)
        prev, nxt, t = buf.get_surrounding_snapshots(90)
        self.assertIsNone(prev)
        self.assertEqual(nxt[0], 100)

    def test_entity_interpolation(self):
        state_a = MockState([0, 0], [0, 0], False, "idle")
        state_b = MockState([10, 20], [2, 4], True, "run")

        # 50%
        res = interpolate_entity(state_a, state_b, 0.5)
        self.assertEqual(res.pos, [5.0, 10.0])
        self.assertEqual(res.velocity, [1.0, 2.0])
        self.assertFalse(res.flip)  # Discrete stays prev

        # 0%
        res = interpolate_entity(state_a, state_b, 0.0)
        self.assertEqual(res.pos, [0.0, 0.0])

        # 100% (Logic handles < curr, so effectively limits towards 1.0)
        res = interpolate_entity(state_a, state_b, 1.0)
        self.assertEqual(res.pos, [10.0, 20.0])


if __name__ == '__main__':
    unittest.main()
