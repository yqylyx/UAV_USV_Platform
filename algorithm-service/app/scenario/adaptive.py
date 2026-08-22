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
        return asdict(self) | {"target_count": self.target_count}


def derive_scenario_plan(uav_count: int, usv_count: int) -> AdaptiveScenarioPlan:
    """Derive mission complexity from the scarcer vehicle domain.

    Target counts are deliberately not user-editable.  A large number of
    aircraft cannot compensate for a missing surface guard fleet (and vice
    versa), so the smaller domain determines how many concurrent tasks are
    safe to create.
    """
    # Phase-two realtime support is intentionally bounded to the tested
    # 15+15 envelope.  Larger requests are clamped instead of creating
    # scenarios whose target count and geometry are not validated.
    uav = max(1, min(15, int(uav_count)))
    usv = max(1, min(15, int(usv_count)))
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
    elif scale <= 15:
        values = (1, 3, 2, 420.0, 320.0)
    else:
        values = (1, 3, 2, 420.0, 320.0)
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
        realtime_tier="PHASE_TWO_REALTIME",
    )
