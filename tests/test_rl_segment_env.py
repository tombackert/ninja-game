"""SegmentEnv (tools/rl): starts from the planned route, seeding, human limits, handoff, guide."""

import pytest

np = pytest.importorskip("numpy")

from tools.rl import segment_env  # noqa: E402
from tools.rl import guide  # noqa: E402
from tools.rl.segment_env import obs_size, route_starts  # noqa: E402
from tools.worlds.planner import dash_climbs  # noqa: E402

LEVEL = 27  # few enemies: quick to load and step


def SegmentEnv(*args, **kwargs):  # noqa: N802
    """The environment without its guide (built once per stretch, minutes):
    the guide has tests of its own below. With the route action (the last)."""
    kwargs.setdefault("use_guide", False)
    kwargs.setdefault("route_action", True)
    return segment_env.SegmentEnv(*args, **kwargs)


def test_every_segment_has_a_start_state_from_the_plan():
    plan, starts = route_starts(LEVEL)
    assert len(starts) == len(plan["segments"])
    assert [s.frame for s in starts] == [start for start, _n in plan["segments"]]


def test_the_route_reaches_the_goal_when_no_enemy_is_near():
    env = SegmentEnv(LEVEL, 10, span=3)  # segments 10-12: no enemy near (threats)
    for seed in range(3):
        assert env.run_plan(seed)["outcome"] == "goal"


def test_observation_has_the_declared_size():
    env = SegmentEnv(LEVEL, 0, span=2)
    obs = env.reset(seed=0)
    assert obs.shape == (obs_size(n_actions=env.n_actions),) == (env.obs_size,)
    assert obs.dtype == np.float32
    obs, reward, done, info = env.step(2)
    assert obs.shape == (env.obs_size,)
    assert isinstance(reward, float)


def test_same_seed_same_episode():
    def run(seed):
        env = SegmentEnv(LEVEL, 0, span=3)
        out = [env.reset(seed)]
        for a in [2, 5, 2, 2, 7, 0, 3, 2] * 4:
            obs, reward, done, info = env.step(a)
            if done:
                break
            out.append(obs)
            out.append(reward)
        return out

    a, b = run(5), run(5)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert np.array_equal(x, y)


def test_the_agent_sees_the_world_as_it_was_reaction_delay_frames_ago():
    env = SegmentEnv(LEVEL, 0, span=3, action_repeat=4, reaction_delay=12)
    newest = segment_env.frame_size()  # the newest grid and the rest of the newest frame
    first = env.reset(seed=1)[:newest]
    # Decisions at frames 4, 8 and 12 still see frame 0
    for _ in range(3):
        obs, _r, done, _i = env.step(2)
        assert not done
        assert np.array_equal(obs[:newest], first)
    obs, _r, _d, _i = env.step(2)
    assert not np.array_equal(obs[:newest], first)  # frame 4: the player has moved

    now = SegmentEnv(LEVEL, 0, span=3, action_repeat=4, reaction_delay=0)
    now.reset(seed=1)
    obs, _r, _d, _i = now.step(2)
    assert not np.array_equal(obs[:newest], first)


def test_waypoints_pay_and_the_goal_ends_the_episode():
    env = SegmentEnv(LEVEL, 10, span=2)
    env.reset(seed=0)
    env._inside = lambda wp: True  # every waypoint is reached on the first frame
    _obs, reward, done, info = env.step(0)
    assert done and info["outcome"] == "goal"
    assert info["waypoints"] == 2 and info["frames"] == 1
    cfg = env.reward_cfg
    assert reward >= 2 * cfg["waypoint"] + cfg["goal"] + cfg["time"]


def test_losing_a_life_ends_the_episode_as_a_death():
    env = SegmentEnv(LEVEL, 0, span=3)
    env.reset(seed=0)
    env.game.player.lives -= 1
    _obs, reward, done, info = env.step(0)
    assert done and info["outcome"] == "death"
    assert reward < 0


def test_the_route_action_plays_the_plan():
    env = SegmentEnv(LEVEL, 0, span=4)
    route = env.n_actions - 1
    for seed in range(2):
        env.reset(seed)
        done = False
        while not done:
            _obs, _r, done, info = env.step(route)
        assert info["outcome"] == env.run_plan(seed)["outcome"]


def test_no_gear_and_no_weapon_whatever_is_equipped():
    from scripts.collectableManager import CollectableManager
    from scripts.settings import settings

    gear, weapon = settings.selected_gear, settings.selected_weapon
    try:
        settings.selected_gear = CollectableManager.GEAR.index("Lucky Charm")
        settings.selected_weapon = CollectableManager.WEAPONS.index("Gun")
        env = SegmentEnv(LEVEL, 0, span=2)
        env.game.cm.lucky_charm = 1
        env.reset(seed=0)
        assert settings.selected_gear == 0 and settings.selected_weapon == 0
        assert env.game.player.lives == 3  # the Lucky Charm would make it 4
    finally:
        settings.selected_gear, settings.selected_weapon = gear, weapon


def test_the_stretch_route_has_no_dash_wall_climb():
    env = SegmentEnv(LEVEL, 10, span=3)
    assert env.route_frames
    assert dash_climbs(env.start_state, env.route_frames, env.solids) == 0


def test_a_jump_that_would_be_the_dash_wall_climb_is_dropped(monkeypatch):
    env = SegmentEnv(LEVEL, 0, span=3)
    env.reset(seed=0)
    monkeypatch.setattr(segment_env, "dash_climb_press", lambda s, dash, solids: True)
    jumps = env.game.player.jumps
    env.step(3)  # jump
    assert env.game.player.jumps == jumps
    assert env.game.player.velocity[1] >= 0


def test_the_route_action_picks_the_route_up_where_the_player_is_on_it():
    env = SegmentEnv(LEVEL, 10, span=3)
    env.reset(seed=0)
    k = len(env.route_frames) // 2  # far from where the route action left it
    env.route_idx = k - 20
    segment_env.set_phys_state(env.game.player, env.route_states[k])
    assert env._route_move() == env.route_frames[k]
    assert env.route_idx == k + 1


def test_a_stretch_ends_at_a_waypoint_the_player_stands_on():
    from tools.worlds.planner import Waypoint

    wps = [Waypoint(0, 0, 0, 0, ground=g) for g in (True, True, False, False, True, False)]
    assert segment_env.handoff_end(wps, 0, 2) == 2  # waypoint 1 is on the ground
    assert segment_env.handoff_end(wps, 1, 2) == 5  # 2 and 3 are mid-air: on to 4
    assert segment_env.handoff_end(wps, 5, 3) == 6  # the level's end


def test_the_planner_takes_over_where_the_route_arrives():
    env = SegmentEnv(LEVEL, 10, span=3)  # no enemy near
    env.reset(seed=0)
    done = False
    while not done:
        _obs, _r, done, info = env.step(env.n_actions - 1)
    assert info["outcome"] == "goal"
    assert env.handoff()


def test_an_episode_can_start_where_the_route_arrives_at_a_later_waypoint():
    env = SegmentEnv(LEVEL, 10, span=3)
    env.reset(seed=0, from_wp=1)
    k = env.route_wp_frame[0]
    assert segment_env.phys_state(env.game.player) == env.route_states[k]
    assert env.next_wp == 1 and env.route_idx == k
    done = False
    while not done:
        _obs, _r, done, info = env.step(env.n_actions - 1)
    assert info["outcome"] == "goal"


def test_progress_along_the_route_pays_once():
    env = SegmentEnv(LEVEL, 10, span=3)
    env.reset(seed=0)
    route = env.n_actions - 1
    _obs, first, _d, _i = env.step(route)
    assert first > 0  # the route moves on: progress
    best = env.best
    segment_env.set_phys_state(env.game.player, env.route_states[0])  # back to the start
    assert env._progress() == 0 and env.best == best


def _jet(on=48, period=120, phase=0):
    return guide.Flames([([(100, 100, 16, 16)], period, on, phase, 108.0, 92.0)])


def test_a_flame_is_deadly_while_it_burns_with_a_margin():
    flames = _jet()
    inside = (100.0, 95.0) + (0.0,) * 10
    assert flames.lethal(inside, 0) and flames.lethal(inside, 47)
    assert flames.lethal(inside, 48 + guide.MARGIN - 1)  # just out: still counted
    assert not flames.lethal(inside, 60)
    assert flames.lethal(inside, 120 - guide.MARGIN)  # about to burn again
    outside = (140.0, 95.0) + (0.0,) * 10
    assert not flames.lethal(outside, 0)


def test_the_guide_answers_for_states_near_one_it_has_seen():
    s = (100.0, 200.0, 0.0, 0.0, 0, 2, False, 0, False, 0, 600, 0)
    g = guide.Guide([(s, True, 0, (1, True, False), None)])
    near = (103.0, 202.0) + s[2:]
    far = (120.0, 200.0) + s[2:]
    assert g.move(near, True, 0) == (1, True, False)
    assert g.move(far, True, 0) is None
    assert g.move(near, True, 1) is None  # another waypoint
    assert g.move(near, False, 0) is None  # in the air


def test_by_a_flame_the_guide_answers_for_the_beat_the_player_is_in():
    flames = _jet()
    s = (100.0, 200.0, 0.0, 0.0, 0, 2, False, 0, False, 0, 600, 0)
    rows = [(s, True, 0, (1, False, False), (0, 30)), (s, True, 0, (-1, False, False), (0, 90))]
    g = guide.Guide(rows, flames)
    assert g.move(s, True, 0, (0, 31)) == (1, False, False)
    assert g.move(s, True, 0, (0, 89)) == (-1, False, False)
    assert g.move(s, True, 0, (0, 60)) is None  # no plan made near that beat


def test_the_guide_leads_back_to_the_route_after_a_detour(monkeypatch, tmp_path):
    monkeypatch.setattr(segment_env, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(segment_env, "GUIDE_ROUNDS", 1)
    monkeypatch.setattr(guide, "PERTURB", 2)
    env = segment_env.SegmentEnv(LEVEL, 10, span=1, route_action=True)  # no enemy near
    assert len(env.guide) > len(env.route_frames)
    route = env.n_actions - 1
    for seed in range(2):
        env.reset(seed)
        for _ in range(2):
            env.step(1)  # walk back, off the route
        done = False
        while not done:
            _obs, _r, done, info = env.step(route)
        assert info["outcome"] == "goal"
        assert info["guided"] > 0


def test_the_agent_sees_its_last_decisions_and_the_newest_grid():
    env = SegmentEnv(LEVEL, 0, span=3, stack=3, reaction_delay=0)
    first = env.reset(seed=0)
    grid = segment_env.GRID_SIZE
    rest = segment_env.frame_size() - grid
    assert first.shape == (segment_env.obs_size(3, env.n_actions),)
    assert np.array_equal(first[grid : grid + rest], first[grid + rest : grid + 2 * rest])  # padded at the start
    obs, _r, _d, _i = env.step(2)
    assert np.array_equal(obs[grid + rest : grid + 2 * rest], first[grid : grid + rest])  # the last one, moved on


def test_every_move_of_the_planner_is_one_of_the_agent():
    assert len(segment_env.ACTIONS) == 12 and len(set(segment_env.ACTIONS)) == 12
    env = SegmentEnv(LEVEL, 10, span=3, route_action=False)
    assert env.n_actions == 12
    env.reset(seed=0)
    taught = env.teacher()  # exactly on the route at the start: the route's move
    assert segment_env.ACTIONS[taught] == tuple((m, bool(j), bool(d)) for m, j, d in [env.route_frames[0]])[0]
    env.game.player.pos[0] += 37.5  # nowhere the route or a guide has been
    assert env.teacher() == -1


def test_the_route_action_knows_where_a_patrol_walks():
    env = SegmentEnv(11, 22, span=3)  # the maze: patrols
    env.reset(seed=0)
    g = env.game
    patrols = [e for e in g.enemies if e.kind.name == "patrol"]
    assert patrols
    for _ in range(5):  # from different points of their walks
        walkers = [segment_env._Walker(e, e.pos[0], e.pos[1], e.flip) for e in patrols]
        for _frame in range(segment_env.LOOK):
            g.apply_inputs([])
            g.step()
            for w, e in zip(walkers, patrols):
                w.step()
                assert abs(w.pos[0] - e.pos[0]) <= 2 and abs(w.pos[1] - e.pos[1]) <= 1


def test_the_route_action_looks_out_for_enemies_on_its_way():
    env = SegmentEnv(LEVEL, 10, span=3)
    env.reset(seed=0)
    s = env.route_states[0]
    ahead = env.route_frames[: segment_env.LOOK]
    on_way = [[(st[0], st[1], 8, 15, False) for st in env.route_states[1 : segment_env.LOOK + 1]]]
    assert env._hits(s, ahead, on_way)  # a shot that meets the player on the route
    assert not env._hits(s, ahead, [[None] * segment_env.LOOK])  # a shot that hit a wall
    far = [[(x + 200, y, w, h, b) for x, y, w, h, b in on_way[0]]]
    assert not env._hits(s, ahead, far)


def test_flames_know_whether_a_way_runs_into_a_burning_jet():
    flames = _jet()  # burns ticks 0-47 of 120, box x 100-116, y 100-116
    through = [(80.0 + 2 * k, 95.0) + (0.0,) * 10 for k in range(30)]  # in the box from frame 7
    assert flames.burns(through, 0, 0)  # arrives while it burns
    assert not flames.burns(through, 0, 60)  # arrives while it is out
    away = [(400.0, 95.0) + (0.0,) * 10] * 30  # out of the jet's reach at once
    assert not flames.burns(away, 0, 0)


def test_the_guide_finds_the_nearest_state_as_a_full_search_does():
    rng = np.random.default_rng(0)
    base = (0.0, 0.0, 0.0, 0.0, 0, 2, False, 0, False, 0, 600, 0)
    rows = []
    for x, y, vx, vy, m in zip(
        rng.uniform(0, 60, 400),
        rng.uniform(0, 60, 400),
        rng.uniform(-1, 1, 400),
        rng.uniform(-1, 1, 400),
        rng.integers(-1, 2, 400),
    ):
        rows.append(((float(x), float(y), float(vx), float(vy)) + base[4:], True, 0, (int(m), False, False), None))
    g = guide.Guide(rows)
    points = np.array([g._point(st) for st, *_ in rows], np.float32)
    for x, y, vx, vy in zip(
        rng.uniform(0, 60, 200), rng.uniform(0, 60, 200), rng.uniform(-1, 1, 200), rng.uniform(-1, 1, 200)
    ):
        s = (float(x), float(y), float(vx), float(vy)) + base[4:]
        d = ((points - np.array(g._point(s), np.float32)) ** 2).sum(1)
        i = int(d.argmin())
        assert g.move(s, True, 0) == (rows[i][3] if d[i] <= guide.RADIUS**2 else None)


def test_a_plan_ends_at_a_state_the_guide_knows_a_whole_way_on_from():
    s = (400.0, 200.0, 0.0, 0.0, 0, 2, False, 0, False, 0, 600, 0)  # out of the jet's reach
    wp = segment_env.Waypoint(0, 0, 0, 0, ground=True, label="far")
    solids = segment_env.terrain(LEVEL)
    goal = guide._Reach(guide.FieldGoal(wp, solids), 0, ({guide.key(s, True, 0)}, set()))
    assert goal.contains(s, True)
    assert not goal.contains(s, False)  # another key
    timed = guide._Reach(guide.FieldGoal(wp, solids), 0, ({guide.key(s, True, 0)}, set()), _jet())
    assert timed.contains(s, True)  # out of the jet's reach
    by_jet = (100.0, 90.0) + s[2:]
    timed.anchors = ({guide.key(by_jet, True, 0)},)
    assert not timed.contains(by_jet, True)  # by the jet the way on depends on the beat


def test_planning_in_one_pool_for_the_build_plans_the_same():
    env = SegmentEnv(LEVEL, 10, span=1)
    seeds = [(st, True, 0, 0) for st in env.route_states[:16:4]]
    alone = guide.plan_from(env.solids, env.waypoints, seeds, procs=2)
    with guide.planners(env.solids, env.waypoints, procs=2):
        pooled = guide.plan_from(env.solids, env.waypoints, seeds, procs=2)
    assert alone == pooled and alone


def _route_guide(env):
    """A guide of just the stretch's route (no planning)."""
    rows, down, wp = [], True, 0
    for st, move in zip(env.route_states, env.route_frames):
        rows.append((st, down, wp, move, None))
        _s, down, _d = segment_env.ph.apply_frame(st, *move, env.solids)
    return guide.Guide(rows)


def test_the_route_action_does_not_look_again_while_its_way_stays_clear(monkeypatch):
    env = SegmentEnv(LEVEL, 10, span=3)
    env.reset(seed=0)
    env.guide = _route_guide(env)
    far = (object(), 10**6, 10**6, False)
    monkeypatch.setattr(env, "_threats", lambda: ([far], [], [], (), 0))  # something to watch, far away
    monkeypatch.setattr(env, "_paths", lambda threats: [[(10**6, 10**6, 8, 8, True)] * segment_env.LOOK])
    looks = []
    real = env._hits
    monkeypatch.setattr(env, "_hits", lambda *a, **k: looks.append(1) or real(*a, **k))
    for _ in range(4):
        env.step(env.n_actions - 1)  # 16 frames on the route
    assert len(looks) == 16 // segment_env.RECHECK


def test_a_player_expects_the_shot_of_a_gunner_whose_walk_ends():
    env = SegmentEnv(11, 9, span=3)
    env.reset(seed=0)
    gunner = next(e for e in env.game.enemies if e.kind.name == "gunner")
    p = env.game.player
    p.pos = [gunner.pos[0] + 60, gunner.pos[1]]  # in front of it, at its height
    gunner.flip, gunner.walking = False, 5  # facing the player, 5 frames left of its walk
    armed = [a for a in env._walker_snapshot()[2] if a[0] is gunner]
    shots = env._expected_shots(armed, age=0)
    assert len(shots) == 1
    x, y, vx, vy, grav, f = shots[0]
    assert f == 5 and vx > 0 and vy == 0
    path = env._shot_path(x, y, vx, vy, grav, f)
    assert path[3] is None and path[5] is not None  # in the air from frame 6 on
    gunner.flip = True  # facing away: no shot at the player
    armed = [a for a in env._walker_snapshot()[2] if a[0] is gunner]
    assert env._expected_shots(armed, age=0) == []
    gunner.flip, gunner.walking = False, 0  # standing: it fires when it next walks, unseen
    armed = [a for a in env._walker_snapshot()[2] if a[0] is gunner]
    assert env._expected_shots(armed, age=0) == []
