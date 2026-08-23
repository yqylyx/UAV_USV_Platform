from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AdaptiveScenarioPlan:
    uav_count: int
    usv_count: int
    effective_scale: int
    protected_count: int
    threat_count: int
    simultaneous_threats: int
    world_width: float
    world_height: float
    realtime_tier: str

    @property
    def target_count(self) -> int:
        return self.protected_count + self.threat_count

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {
            "target_count": self.target_count,
            "plan_version": "adaptive-scenario-v3",
        }


def derive_scenario_plan(uav_count: int, usv_count: int) -> AdaptiveScenarioPlan:
    """Derive mission complexity from the scarcer vehicle domain.

    Target counts are deliberately not user-editable.  A large number of
    aircraft cannot compensate for a missing surface guard fleet (and vice
    versa), so the smaller domain determines how many concurrent tasks are
    safe to create.
    """
    # The protocol and Unity runtime expose the same 1..128 contract.  Never
    # silently discard devices: counts above the realtime acceptance envelope
    # remain capacity-mode simulations, but every configured code is retained
    # and receives an explicit role and pose.
    uav = max(1, min(128, int(uav_count)))
    usv = max(1, min(128, int(usv_count)))
    scale = min(uav, usv)
    if scale <= 5:
        # A 120 m threat offset plus an 80 m visible escape cannot fit inside
        # the former 240 x 200 m arena after the 28 m shore inset.  Use the
        # same open-water extent as the next tier so the enemy never has to
        # reverse through the convoy merely to complete its chase distance.
        values = (1, 1, 1, 360.0, 280.0)
    elif scale <= 9:
        values = (1, 1, 1, 360.0, 280.0)
    elif scale <= 14:
        values = (1, 2, 2, 360.0, 280.0)
    elif scale <= 19:
        values = (1, 3, 2, 420.0, 320.0)
    elif scale <= 24:
        values = (2, 3, 2, 520.0, 400.0)
    elif scale <= 30:
        values = (2, 4, 3, 600.0, 460.0)
    else:
        protected = min(4, 2 + max(0, scale - 31) // 32)
        threats = min(8, 4 + max(0, scale - 31) // 16)
        simultaneous = min(4, max(2, (threats + 1) // 2))
        width = 600.0 + min(600.0, max(0, scale - 30) * 8.0)
        height = 460.0 + min(440.0, max(0, scale - 30) * 6.0)
        values = (protected, threats, simultaneous, width, height)
    protected, threats, simultaneous, width, height = values
    return AdaptiveScenarioPlan(
        uav_count=uav,
        usv_count=usv,
        effective_scale=scale,
        protected_count=int(protected),
        threat_count=int(threats),
        simultaneous_threats=int(simultaneous),
        world_width=float(width),
        world_height=float(height),
        realtime_tier="PHASE_TWO_REALTIME" if scale <= 30 else "CAPACITY_ONLY",
    )
