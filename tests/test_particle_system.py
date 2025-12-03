from scripts.particle_system import ParticleSystem


class DummyGame:
    def __init__(self):
        # Minimal assets needed by Particle constructor
        class DummyAnim:
            def __init__(self):
                self.frame = 0
                self.done = False

            def copy(self):
                return self

            def update(self):
                # Mark done after a couple frames
                self.frame += 1
                if self.frame > 1:
                    self.done = True

            def img(self):
                return None

        self.assets = {"particle/particle": DummyAnim(), "particle/leaf": DummyAnim()}


def test_particle_system_spawn_and_update():
    g = DummyGame()
    ps = ParticleSystem(g)
    # Spawn a spark and particle
    ps.spawn_spark((0, 0), angle=0.0, speed=1.0)
    ps.spawn_particle("particle", (0, 0))
    assert len(ps.sparks) == 1
    assert len(ps.particles) == 1
    # Run enough updates for both to expire (spark speed reduces to 0)
    for _ in range(20):  # enough frames for particle anim + spark decay
        ps.update()
        if not ps.sparks and not ps.particles:
            break
    assert len(ps.particles) == 0  # particle animation done
    # spark should also be removed once speed hits zero
    assert len(ps.sparks) == 0
