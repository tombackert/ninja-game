from scripts.rollback_buffer import RollbackBuffer
from scripts.snapshot import SnapshotService, SimulationSnapshot
from scripts.training_env import TrainingEnv
import copy


class PredictionReconciliationService:
    def __init__(self, game, rollback_buffer: RollbackBuffer):
        self.game = game
        self.rollback_buffer = rollback_buffer
        self.current_tick = 0

    def apply_input(self, inputs):
        """Apply local input and advance simulation one tick."""
        # This mirrors TrainingEnv.step's logic but for the live game
        # For now, we assume the game is already updated externally or here.
        # Let's assume this method is called *before* the game update to register intent,
        # or *wrapping* the game update.

        # 1. Store current state (before update) as the snapshot for 'current_tick'
        #    Wait, usually we store the state *after* the update of tick T.
        #    Let's say we are at tick T. We apply input T. We produce state T+1.
        pass

    def on_authoritative_snapshot(self, auth_snapshot: SimulationSnapshot):
        """Handle incoming server snapshot."""
        tick = auth_snapshot.tick

        # 1. Get local history for that tick
        local_frame = self.rollback_buffer.get(tick)

        if not local_frame:
            # Too old or future?
            return

        # 2. Compare
        # Basic comparison of player position for now
        # In real implementation, compare hash or critical fields

        # Hacky comparison: Serialize both and check equality?
        # Or checking specific fields manually.

        # We need to verify if the auth_snapshot matches our local_frame.snapshot
        mismatch = False

        # Simple check: Player 0 pos
        local_p = local_frame.snapshot.players[0] if local_frame.snapshot.players else None
        auth_p = auth_snapshot.players[0] if auth_snapshot.players else None

        if local_p and auth_p:
            if local_p.pos != auth_p.pos:
                mismatch = True
        elif local_p != auth_p:
            mismatch = True

        if mismatch:
            print(f"Reconciliation Triggered at tick {tick}!")
            # 3. Rollback
            # Restore auth state
            SnapshotService.restore(self.game, auth_snapshot)

            # 4. Re-simulate inputs from tick+1 to current_tick
            # We need inputs for [tick, tick+1, ... current_tick-1]
            # to reach current state again.

            # Wait, local_frame at 'tick' contains the state *at* tick.
            # And the inputs used to *produce* that state (or inputs *at* that tick?).
            # RollbackBuffer typically stores (State_T, Input_T).

            re_sim_tick = tick
            while re_sim_tick < self.rollback_buffer.newest_tick:  # type: ignore
                # Get inputs for next step
                # We need the input that was applied *after* state 're_sim_tick'
                # to produce 're_sim_tick + 1'.

                # If buffer stores (State_T, Input_T), does Input_T produce State_T or State_T+1?
                # Standard convention: Update(State_T, Input_T) -> State_T+1.

                next_frame = self.rollback_buffer.get(re_sim_tick + 1)
                if not next_frame:
                    break  # Should not happen if buffer contiguous

                inputs = next_frame.inputs  # Input used to reach T+1?
                # Actually RollbackBuffer structure in `scripts/training_env.py` logic isn't explicitly defined yet
                # regarding input/state relationship.

                # Let's assume Input_T is what we wanted to execute at T.
                self._apply_inputs_and_step(inputs)

                # Update buffer with CORRECTED state
                new_snap = SnapshotService.capture(self.game)
                new_snap.tick = re_sim_tick + 1
                self.rollback_buffer.push(new_snap, inputs)  # Overwrite

                re_sim_tick += 1

    def _apply_inputs_and_step(self, inputs):
        # Re-use TrainingEnv's logic or Game's internal input mapping
        # Ideally Game has a method `apply_inputs(list)` and `update()`.

        g = self.game
        g.movement = [False, False]
        for key in inputs:
            if key == "left":
                g.movement[0] = True
            elif key == "right":
                g.movement[1] = True
            elif key == "jump":
                g.player.jump()
            elif key == "dash":
                g.player.dash()
            elif key == "shoot":
                g.player.shoot()

        # Tick physics
        # We can extract the step logic from TrainingEnv or duplicate it temporarily.
        # For this feature, I will rely on `game.player.update` etc.

        movement_vec = (g.movement[1] - g.movement[0], 0)
        g.player.update(g.tilemap, movement_vec)
        # (Skipping full entity loop for brevity in this snippet, focusing on player correction)
        # In full implementation, this would call game.update()
