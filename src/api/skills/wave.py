# DEPRECATED compatibility shim — use maiw_skills.wave directly. Remove by Phase 9.
from maiw_skills.wave.skills import (  # noqa: F401
    ExecuteWaveReprioritizationSkill,
    ProposeWaveReprioritizationSkill,
    WaveGetSkill,
    WaveRiskSkill,
    get_execute_wave_reprioritization_skill,
    get_propose_wave_reprioritization_skill,
    get_wave_get_skill,
    get_wave_risk_skill,
)
