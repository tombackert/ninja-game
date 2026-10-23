"""Tests for the one-physics-step-per-input model (ClientState.take_steps,
HeadlessGame._pending_steps).

The key property: however late, reordered or lost the input packets
arrive, the server's player ends up exactly where the client predicted it
after the same input.
"""

import random
import unittest

import pygame

from scripts.network.client_state import (
    HOLE_WAIT_TICKS,
    MAX_INPUT_AHEAD,
    MAX_INPUT_BACKLOG,
    MAX_STEPS_PER_TICK,
    ClientState,
)
from scripts.network.headless_game import HeadlessGame

L, R, IDLE = [True, False], [False, True], [False, False]


def setUpModule():
    pygame.init()


def _client() -> ClientState:
    return ClientState(player_id=1, player_name="P", address=("127.0.0.1", 1))


def _ticks(steps):
    return [t for t, _, _ in steps]


class TestTakeSteps(unittest.TestCase):
    def test_one_step_per_input_in_order(self):
        c = _client()
        for tick in (10, 11, 12):
            c.receive_input(tick, R, [])
            self.assertEqual(c.take_steps(), [(tick, R, [])])
        self.assertEqual(c.ack_tick, 12)

    def test_waits_while_no_input_arrived(self):
        c = _client()
        c.receive_input(10, R, [], arrival=1.0)
        c.take_steps()
        c.count_tick_inputs()
        self.assertEqual(c.take_steps(), [])
        self.assertEqual(c.tick_counts["no_step"], 1)

    def test_burst_catches_up_at_most_max_steps_per_tick(self):
        c = _client()
        for tick in range(10, 15):
            c.receive_input(tick, R, [], arrival=1.0)
        runs = [_ticks(c.take_steps()) for _ in range(4)]
        self.assertEqual(MAX_STEPS_PER_TICK, 2)
        self.assertEqual(runs, [[10, 11], [12, 13], [14], []])
        self.assertEqual(c.tick_counts["multi_step"], 2)

    def test_history_covers_a_lost_packet(self):
        c = _client()
        c.receive_input(10, R, [])
        self.assertEqual(_ticks(c.take_steps()), [10])
        # Packet 11 is lost; 12 carries the movement of 10 and 11
        c.receive_input(12, L, [], history=[R, IDLE])
        self.assertEqual(c.take_steps(), [(11, IDLE, []), (12, L, [])])
        self.assertEqual(c.tick_counts["filled"], 0)

    def test_reordered_packets_run_in_tick_order(self):
        c = _client()
        c.receive_input(10, R, [])
        c.take_steps()
        c.receive_input(12, L, [])
        c.receive_input(11, IDLE, [])
        self.assertEqual(c.take_steps(), [(11, IDLE, []), (12, L, [])])

    def test_duplicate_packet_runs_once(self):
        c = _client()
        c.receive_input(10, R, [])
        c.receive_input(10, R, [])
        self.assertEqual(_ticks(c.take_steps()), [10])
        c.receive_input(10, R, [])
        self.assertEqual(c.take_steps(), [])

    def test_hole_is_filled_with_the_last_movement_after_waiting(self):
        c = _client()
        c.receive_input(10, R, [])
        c.take_steps()
        c.receive_input(12, L, [])  # 11 never arrives, no history
        for _ in range(HOLE_WAIT_TICKS):
            self.assertEqual(c.take_steps(), [])
        self.assertEqual(c.take_steps(), [(11, R, []), (12, L, [])])
        self.assertEqual(c.tick_counts["filled"], 1)

    def test_action_runs_in_its_own_tick(self):
        c = _client()
        # Packet 10 (with the jump) is lost; 11 re-sends the jump with its tick
        c.receive_input(9, IDLE, [])
        c.take_steps()
        c.receive_input(11, R, [[1, "jump", 10]], history=[R])
        self.assertEqual(c.take_steps(), [(10, R, ["jump"]), (11, R, [])])
        # Re-sent once more: deduplicated
        c.receive_input(12, R, [[1, "jump", 10]])
        self.assertEqual(c.take_steps(), [(12, R, [])])

    def test_late_action_runs_with_the_next_step(self):
        c = _client()
        c.receive_input(10, R, [])
        c.take_steps()
        c.receive_input(12, R, [])
        for _ in range(HOLE_WAIT_TICKS):
            c.take_steps()
        c.take_steps()  # 11 filled in, 12 ran
        c.receive_input(13, R, [[1, "jump", 11]])
        self.assertEqual(c.take_steps(), [(13, R, ["jump"])])
        self.assertEqual(c.tick_counts["late_actions"], 1)

    def test_overlong_backlog_is_skipped(self):
        c = _client()
        for tick in range(0, MAX_INPUT_BACKLOG + 40):
            c.receive_input(tick, R, [])
        steps = c.take_steps()
        self.assertEqual(steps[0][0], 40)
        self.assertEqual(c.tick_counts["dropped"], 40)

    def test_input_far_ahead_is_ignored(self):
        c = _client()
        c.receive_input(10, R, [])
        c.take_steps()
        c.receive_input(10 + MAX_INPUT_AHEAD + 1, R, [])
        self.assertEqual(c.take_steps(), [])
        self.assertEqual(c.input_queue, {})

    def test_hold_reference_is_the_arrival_of_the_input_that_ran(self):
        c = _client()
        c.receive_input(10, R, [], arrival=100.0)
        c.receive_input(11, R, [], arrival=100.5)
        c.take_steps(max_steps=1)
        self.assertEqual(c.last_processed_arrival, 100.0)
        self.assertEqual(c.last_input_arrival, 100.5)


class TestHeadlessSteps(unittest.TestCase):
    def setUp(self):
        self.game = HeadlessGame(level=0)
        self.game.enemies = []
        self.player = self.game.add_player(player_id=1)
        for _ in range(30):  # land on the ground
            self.game._pending_steps[1] = [((0, 0), [])]
            self.game.simulate_tick()

    def test_no_step_leaves_the_player_where_it_is(self):
        before = list(self.player.pos)
        self.game._pending_steps[1] = [((1, 0), ["jump"])]
        self.game.simulate_tick()
        mid_jump = list(self.player.pos)
        self.assertNotEqual(mid_jump, before)
        self.game._pending_steps[1] = []
        self.game.simulate_tick()
        self.assertEqual(self.player.pos, mid_jump)

    def test_two_steps_equal_two_ticks(self):
        other = HeadlessGame(level=0)
        other.enemies = []
        twin = other.add_player(player_id=1)
        for _ in range(30):
            other._pending_steps[1] = [((0, 0), [])]
            other.simulate_tick()
        self.game._pending_steps[1] = [((1, 0), ["jump"]), ((1, 0), [])]
        self.game.simulate_tick()
        for step in ([((1, 0), ["jump"])], [((1, 0), [])]):
            other._pending_steps[1] = step
            other.simulate_tick()
        self.assertEqual(self.player.pos, twin.pos)
        self.assertEqual(self.player.velocity, twin.velocity)

    def test_players_without_steps_use_pending_inputs(self):
        before = self.player.pos[0]
        for _ in range(10):
            self.game._pending_inputs[1] = (1, 0)
            self.game.simulate_tick()
        self.assertGreater(self.player.pos[0], before)


def _pattern(k: int):
    """Runner-like input: direction changes, pauses, jumps, dashes."""
    move = R if (k // 40) % 2 == 0 else L
    if (k // 97) % 3 == 2:
        move = IDLE
    actions = []
    if k % 23 == 5:
        actions.append("jump")
    if k % 61 == 30:
        actions.append("dash")
    return move, actions


def _vector(move):
    return (int(move[1]) - int(move[0]), 0)


class TestServerMatchesPrediction(unittest.TestCase):
    """The server's player is exactly where the client predicted it."""

    TICKS = 360

    def _predict(self):
        client = HeadlessGame(level=0)
        client.enemies = []
        player = client.add_player(player_id=1)
        positions = []
        for k in range(self.TICKS):
            move, actions = _pattern(k)
            client._pending_steps[1] = [(_vector(move), actions)]
            client.simulate_tick()
            positions.append((list(player.pos), list(player.velocity)))
        return positions

    def _serve(self, seed: int, loss: float, delays):
        """Deliver the packets with random delays (in ticks) and loss; compare after every tick."""
        rng = random.Random(seed)
        predicted = self._predict()
        server = HeadlessGame(level=0)
        server.enemies = []
        player = server.add_player(player_id=1)
        state = _client()
        inbox = {}
        seq = 0
        action_log = []  # (seq, name, tick), re-sent until the server ran the tick
        for k in range(self.TICKS):
            move, actions = _pattern(k)
            for name in actions:
                seq += 1
                action_log.append((seq, name, k))
            history = [_pattern(t)[0] for t in range(max(0, k - 3), k)]
            packet = (k, move, [[s, n, t] for s, n, t in action_log if t > state.ack_tick], history)
            if k == 0 or rng.random() >= loss:
                inbox.setdefault(k + (0 if k == 0 else rng.choice(delays)), []).append(packet)
        checked = 0
        for tick in range(self.TICKS + 20):
            arrivals = inbox.pop(tick, [])
            rng.shuffle(arrivals)  # reordering within a tick
            for k, move, actions, history in arrivals:
                state.receive_input(k, move, actions, arrival=1.0, history=history)
            state.count_tick_inputs()
            steps = state.take_steps()
            server._pending_steps[1] = [(_vector(m), a) for _, m, a in steps]
            server.simulate_tick()
            if steps:
                pos, vel = predicted[state.ack_tick]
                self.assertEqual(player.pos, pos, f"tick {state.ack_tick}")
                self.assertEqual(player.velocity, vel, f"tick {state.ack_tick}")
                checked += 1
        self.assertEqual(state.ack_tick, self.TICKS - 1)
        self.assertEqual(state.tick_counts["filled"], 0)
        return checked, state.tick_counts

    def test_lossless_jitter(self):
        checked, counts = self._serve(seed=1, loss=0.0, delays=[0, 0, 1, 1, 2, 3])
        self.assertGreater(checked, self.TICKS // 2)
        self.assertGreater(counts["multi_step"], 0)  # bursts did happen

    def test_jitter_with_loss_and_reordering(self):
        checked, counts = self._serve(seed=7, loss=0.1, delays=[0, 1, 1, 2, 4])
        self.assertGreater(checked, self.TICKS // 2)
        self.assertGreater(counts["no_step"], 0)


if __name__ == "__main__":
    unittest.main()
