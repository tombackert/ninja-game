import pytest

from scripts.training_env import TrainingEnv


def test_training_env_determinism():
    # Run 1
    env1 = TrainingEnv(seed=42)
    obs1 = env1.reset()
    rewards1 = []
    for _ in range(10):
        # Action 2: Right
        o, r, d, _ = env1.step(2)
        rewards1.append(r)
        if d:
            break

    # Run 2
    env2 = TrainingEnv(seed=42)
    obs2 = env2.reset()
    rewards2 = []
    for _ in range(10):
        o, r, d, _ = env2.step(2)
        rewards2.append(r)
        if d:
            break

    # Verify
    assert obs1 == obs2
    assert rewards1 == rewards2


def test_training_env_step():
    env = TrainingEnv()
    env.reset()

    # Step with action
    obs, reward, done, info = env.step(3)  # Jump

    assert "self" in obs
    assert isinstance(reward, float)
    assert not done
    assert info["tick"] == 1
    assert reward == 0.01  # Default survival reward


def test_losing_a_life_is_penalized_whatever_the_player_id():
    env = TrainingEnv(seed=42, level_id=1)
    env.reset()
    assert env.game.player.id != 0  # the enemies of this level take the first ids

    env.game.player.lives -= 1
    _, reward, _, _ = env.step(0)

    config = env.reward_shaper.config
    assert reward == pytest.approx(config["survival_reward"] + config["damage_penalty"])
