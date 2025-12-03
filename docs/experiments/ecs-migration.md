# ADR 001: Architecture Decision regarding ECS Migration

**Status:** Accepted
**Date:** 2025-12-01
**Context:** Issue 32 proposed an exploratory assessment of migrating gameplay systems (specifically particles and projectiles) to an Entity Component System (ECS) architecture to improve performance and decoupling.

## Experiment
We implemented two prototypes in `experiments/ecs/`:
1. `ecs_proto.py`: A dictionary-based ECS handling Position, Velocity, and Lifetime components.
2. `oop_proto.py`: A standard OOP approach using `__slots__` and list filtering, mimicking the current engine.

Both simulations updated 5,000 entities over 100 frames.

## Results
| Architecture | Total Time | Avg Step Time |
|--------------|------------|---------------|
| ECS (Dict)   | 0.0482s    | 0.48ms        |
| OOP (Slots)  | 0.0384s    | 0.38ms        |

## Analysis
The OOP approach proved approximately **20% faster** than the pure Python ECS implementation.

Reasons:
1. **Interpreter Overhead:** Python's dictionary lookups (hashing/probing) required for component retrieval in ECS ("joining" component arrays) incur significant overhead.
2. **Reference Indirection:** Python objects are references. ECS in Python does not easily achieve the CPU cache locality benefits (SoA - Structure of Arrays) seen in C++/Rust without using libraries like `numpy` or `struct` arrays, which introduce their own marshalling costs for game logic.
3. **Simplicity:** The OOP approach (`p.update()`) uses direct attribute access which is highly optimized in Python, especially with `__slots__`.

## Decision
We will **NOT** proceed with a full ECS migration for the core engine at this stage.

*   **Performance:** There is no performance gain to justify the rewrite; in fact, it may introduce a regression.
*   **Complexity:** Introducing an ECS would require a significant architectural shift for little tangible benefit in a project of this scale.
*   **Alternative:** We will continue to use the "SystemService" pattern (e.g., `ParticleSystem`, `ProjectileSystem`) which centralizes update loops (array-of-structures style) without strictly decomposing entities into generic ID+Component bags. This offers a good balance of decoupling and performance.

## Future Considerations
If performance becomes a bottleneck with >10,000 entities, we should investigate `numpy`-based vectorization or C-extensions (e.g., Cython/Rust bindings) rather than a pure Python ECS.
