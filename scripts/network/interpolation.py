from collections import deque
from typing import Optional, Tuple, Protocol, Any, Dict
from dataclasses import dataclass, asdict

@dataclass
class InterpolatedState:
    pos: list[float]
    velocity: list[float]
    flip: bool
    action: str
    anim_frame: float # Float to allow smooth animation interpolation if needed

class Timestamped(Protocol):
    tick: int
    # We might need a real timestamp (float seconds) or derive it from tick * dt
    
class SnapshotBuffer:
    """
    Stores a history of snapshots to allow retrieving a state at a specific 'render time'.
    """
    def __init__(self, max_size: int = 20):
        self.buffer: deque = deque(maxlen=max_size)
    
    def push(self, tick: int, state: Any):
        """
        Push a new snapshot state with its associated tick/timestamp.
        State can be a full SimulationSnapshot or a specific EntitySnapshot.
        """
        # Maintain sorted order? Assuming push is chronological.
        # If network packets arrive out of order, we might need a sorted list.
        # For now, assuming ordered insertion or robust enough.
        if self.buffer and tick < self.buffer[-1][0]:
            # Out of order packet, ignore or insert sorted (ignoring for MVP)
            return 
        self.buffer.append((tick, state))

    def get_surrounding_snapshots(self, target_tick: float) -> Tuple[Optional[Tuple[int, Any]], Optional[Tuple[int, Any]], float]:
        """
        Finds the two snapshots surrounding the target_tick.
        Returns (prev_snap, next_snap, t) where t is the interpolation factor [0, 1].
        """
        if not self.buffer:
            return None, None, 0.0
            
        # Case: Target is newer than newest snapshot (Lag/Prediction needed)
        newest_tick, newest_state = self.buffer[-1]
        if target_tick >= newest_tick:
            return (newest_tick, newest_state), None, 0.0
            
        # Case: Target is older than oldest snapshot (History lost)
        oldest_tick, oldest_state = self.buffer[0]
        if target_tick < oldest_tick:
            return None, (oldest_tick, oldest_state), 0.0
            
        # Case: Target is within buffer
        # Iterate backwards (assuming target is usually close to newest)
        for i in range(len(self.buffer) - 1, 0, -1):
            curr_tick, curr_state = self.buffer[i]
            prev_tick, prev_state = self.buffer[i-1]
            
            if prev_tick <= target_tick < curr_tick:
                # Found the interval
                dt = curr_tick - prev_tick
                t = (target_tick - prev_tick) / dt
                return (prev_tick, prev_state), (curr_tick, curr_state), t
                
        return None, None, 0.0

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def lerp_list(a: list[float], b: list[float], t: float) -> list[float]:
    return [lerp(v1, v2, t) for v1, v2 in zip(a, b)]

def interpolate_entity(prev_state, next_state, t: float) -> InterpolatedState:
    """
    Interpolates between two entity states.
    Assumes state objects have pos, velocity, flip, action.
    """
    # Position and Velocity are continuous
    i_pos = lerp_list(prev_state.pos, next_state.pos, t)
    i_vel = lerp_list(prev_state.velocity, next_state.velocity, t)
    
    # Discrete properties snap to nearest or keep previous?
    # Usually flip/action change instantly.
    # We can switch at t > 0.5 or keep prev.
    # Let's stick to prev for stability until next keyframe.
    i_flip = prev_state.flip
    i_action = prev_state.action
    
    # Animation frame? If we have it.
    # Assuming external animation clock, but if snapshot has frame:
    # i_frame = lerp(prev.frame, next.frame, t)
    i_frame = 0.0 
    
    return InterpolatedState(i_pos, i_vel, i_flip, i_action, i_frame)
