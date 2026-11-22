"""One-time conversion of retired panel recipes into ordinary editable settings."""
from copy import deepcopy


def convert_state(state):
    state = deepcopy(state)
    panel = state.pop('publication_panel', None)
    controls = state.setdefault('controls', {})
    enabled = controls.pop('publication_panel_check', True)
    if not panel or not enabled:
        return state
    style = state.setdefault('style', {})
    kind = panel.get('kind')
    style.update(title=panel.get('title',''), font_family='DejaVu Sans', font_size=7.5,
                 label_size=8., tick_size=7., title_size=8., legend_size=6.8,
                 size_mode='Custom', width=3.2, height=2.4, grid='Hide')
    charts = {'cbe':'Charge balance', 'screening':'SAR intervals',
              'validation':'Held-out predictions', 'rmse':'RMSE comparison'}
    if kind in charts:
        controls['assessment_chart_combo'] = charts[kind]
    if kind == 'pearson':
        controls['correlation_annotate_check'] = False
    if kind == 'si_box':
        controls.update(si_distribution_points_check=False, si_class_colors_check=False)
    if kind == 'si_scatter':
        controls['si_class_colors_check'] = False
    if kind in ('chromium_vi', 'wqi_map', 'indices'):
        fields = panel['chromium_columns']
        controls.update(point_threshold_column_combo=fields['total'], point_threshold_operator_combo='>',
                        point_threshold_spin=panel['total_Cr_guideline_ug_L'],
                        point_threshold_color_edit='#b52f3b', point_threshold_size_spin=64.,
                        point_bounds_check=False, point_labels_combo='Highlighted only')
        if kind != 'indices':
            controls['point_geographic_check'] = True
            for key in ('xlim', 'ylim', 'xticks', 'yticks'):
                if key in panel:
                    name = key[0] + ('_limits' if key.endswith('lim') else '_ticks')
                    style[name] = ', '.join(map(str, panel[key]))
            style.update(x_tick_format='.2f', y_tick_format='.2f')
        if kind == 'indices':
            controls.update(wq_view_combo='WQI versus DWQI scatter')
            state['active_plot'] = 'index_scatter'
        if kind == 'chromium_vi':
            controls.update(map_value_combo=fields['vi'], map_label_combo=fields['sample'],
                            point_scale_combo='Logarithmic', point_zero_check=True, point_zero_note_check=True,
                            point_limits_edit=', '.join(map(str, panel['positive_colour_limits'])),
                            point_ticks_edit=', '.join(map(str, panel['positive_colour_ticks'])),
                            point_label_offsets_edit='; '.join(f'{key}:{pair[0]},{pair[1]}' for key,pair in panel.get('label_offsets',{}).items()))
    if kind == 'chromium_total':
        state['variables'] = [panel['chromium_columns']['total'], panel['chromium_columns']['vi']]
        state['active_plot'] = 'Measured series · source rows'
        controls.update(diagram_combo=state['active_plot'], series_threshold_check=True,
                        series_order_edit='; '.join(state['variables']),
                        series_threshold_spin=panel['total_Cr_guideline_ug_L'],
                        series_names_edit='Total Cr, Cr(VI)', series_threshold_label_edit='Total Cr threshold')
    return state


def migrate(project):
    for module, old in list(project.modules.items()):
        converted = convert_state(old)
        profiles = {}
        for key, profile in old.get('plot_profiles', {}).items():
            value = convert_state(profile)
            profiles[value.pop('active_plot', key)] = value
        converted['plot_profiles'] = profiles
        recipe = old.get('publication_panel', {})
        if module == 'maps' and recipe.get('kind') == 'chromium_total' and old.get('controls',{}).get('publication_panel_check',True):
            project.modules['statistics'] = converted
            del project.modules[module]
            if project.last_module == module:
                project.last_module = 'statistics'
        else:
            project.modules[module] = converted
    return project
