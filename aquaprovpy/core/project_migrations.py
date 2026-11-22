"""Move saved statistical plot settings into the Statistics workspace."""

from copy import deepcopy
from .catalog import GROUNDWATER_DIAGRAMS, STATISTICS_DIAGRAMS


def separate_statistics(project):
    """Move statistical profiles out of older Groundwater settings in memory.

    Existing Statistics profiles take precedence. The caller decides when
    to save the migrated project.
    """
    legacy = project.modules.get('groundwater', {})
    profiles = legacy.get('plot_profiles', {})
    if not isinstance(profiles, dict) or any(not isinstance(v, dict) for v in profiles.values()):
        raise ValueError('Invalid saved plot settings.')
    active = legacy.get('controls', {}).get('diagram_combo', legacy.get('active_plot'))
    statistical = {key: deepcopy(value) for key, value in profiles.items() if key in STATISTICS_DIAGRAMS}
    if active in STATISTICS_DIAGRAMS:
        # The active plot's controls may be newer than its saved profile.
        statistical[active] = deepcopy({key: value for key, value in legacy.items()
                                       if key not in ('active_plot', 'plot_profiles')})
    if not statistical:
        return project

    if 'statistics' not in project.modules:
        selected = active if active in STATISTICS_DIAGRAMS else next(iter(statistical))
        state = deepcopy(statistical[selected])
        state.setdefault('controls', {})['diagram_combo'] = selected
        state.update(active_plot=selected, plot_profiles=statistical)
        project.modules['statistics'] = state
    else:
        # A newer Statistics workspace takes precedence over legacy duplicates.
        saved = project.modules['statistics'].setdefault('plot_profiles', {})
        for name, profile in statistical.items():
            saved.setdefault(name, profile)

    remaining = {key: deepcopy(value) for key, value in profiles.items() if key in GROUNDWATER_DIAGRAMS}
    if active in STATISTICS_DIAGRAMS:
        selected = next(iter(remaining), GROUNDWATER_DIAGRAMS[0])
        state = deepcopy(remaining.get(selected, {}))
        state.setdefault('controls', {})['diagram_combo'] = selected
        state.update(active_plot=selected, plot_profiles=remaining)
        project.modules['groundwater'] = state
        if project.last_module == 'groundwater':
            project.last_module = 'statistics'
    else:
        legacy['plot_profiles'] = remaining
    return project
