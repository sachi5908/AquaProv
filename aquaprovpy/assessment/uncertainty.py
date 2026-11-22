"""Conditional Monte Carlo propagation and follow-up assay priorities."""

import numpy as np
import pandas as pd

from .measurements import CORE, WEIGHTS, CHARGES
from ..irrigation import classify_ussl, classify_wilcox
from .censoring import draw_left_censored, validate_censor_model
from .decision import expected_value


WHO_SCREENING = {
    'id': 'WHO-2022-selected-chemicals-v1',
    'source': 'WHO Guidelines for drinking-water quality, fourth edition incorporating the first and second addenda (2022)',
    'url': 'https://www.who.int/publications/i/item/9789240045064',
    'purpose': 'Selected chemical screening values; not a complete drinking-water compliance assessment.',
    'thresholds': [
        {'analyte': 'NO3', 'value': 50.0, 'unit': 'mg/L', 'basis': 'species'},
        {'analyte': 'F', 'value': 1.5, 'unit': 'mg/L', 'basis': 'species'},
        {'analyte': 'Cr_total', 'value': 0.05, 'unit': 'mg/L', 'basis': 'species'},
        {'analyte': 'Ni', 'value': 0.07, 'unit': 'mg/L', 'basis': 'species'},
    ],
}


def validate_profile(profile):
    from .measurements import factor
    if not isinstance(profile, dict) or not all(profile.get(x) for x in ('id', 'source', 'thresholds')):
        raise ValueError('A threshold profile needs id, source and thresholds.')
    seen = set()
    for t in profile['thresholds']:
        a = t['analyte']
        if a in seen:
            raise ValueError('Use one upper threshold per analyte in a profile.')
        seen.add(a)
        if t.get('unit') != 'mg/L' or t.get('basis') != 'species':
            raise ValueError('Thresholds must use mg/L of the named species.')
        factor(a, t['unit'], t['basis'])
        if not np.isfinite(t['value']) or t['value'] <= 0:
            raise ValueError('Threshold values must be finite and positive.')
    return profile


def validate_options(draws, seed, relative_sd, censoring, uncertainty):
    if isinstance(draws, bool) or not isinstance(draws, int) or not 200 <= draws <= 20000:
        raise ValueError('Use 200 to 20,000 Monte Carlo draws.')
    if not isinstance(seed, int) or seed < 0:
        raise ValueError('Seed must be a nonnegative integer.')
    if not np.isfinite(relative_sd) or not 0 <= relative_sd <= 1:
        raise ValueError('Scenario relative SD must be between 0 and 1.')
    if uncertainty not in ('fixed', 'scenario', 'laboratory'):
        raise ValueError('Choose fixed, scenario or laboratory uncertainty.')
    if censoring not in ('exclude', 'uniform', 'half_limit', 'lognormal'):
        raise ValueError('Choose exclude, uniform, half_limit or lognormal censoring.')


def draw_observation(obs, rng, count, relative_sd, censoring, uncertainty, censor_model=None):
    if obs.status == 'left_censored' and np.isfinite(obs.limit):
        if censoring == 'uniform':
            return rng.uniform(0, obs.limit, count)
        if censoring == 'half_limit':
            return np.full(count, obs.limit / 2)
        if censoring == 'lognormal' and censor_model is not None:
            return draw_left_censored(obs.limit, censor_model, rng, count)
        return None
    if obs.status not in ('detected', 'zero'):
        return None
    mean = obs.value
    sd = mean * relative_sd if uncertainty == 'scenario' else obs.sd if uncertainty == 'laboratory' else 0
    if not np.isfinite(sd):
        return None
    if mean == 0 and sd > 0:
        return None  # A nonnegative distribution cannot have zero mean and positive SD.
    if sd == 0:
        return np.full(count, mean)
    sigma2 = np.log1p((sd / mean) ** 2)
    return rng.lognormal(np.log(mean) - sigma2 / 2, np.sqrt(sigma2), count)


def draw_group(group, rng, count, relative_sd, censoring, uncertainty, correlation=0.0, censor_models=None):
    """Equicorrelated log errors; censor draws remain separate scenarios."""
    if not np.isfinite(correlation) or not 0 <= correlation < 1:
        raise ValueError('Shared log-error correlation must be in [0,1).')
    samples, skipped, correlated = {}, [], []
    for obs in group.itertuples():
        sd = obs.value*relative_sd if uncertainty == 'scenario' else obs.sd if uncertainty == 'laboratory' else 0
        if correlation and obs.status == 'detected' and np.isfinite(sd) and sd > 0:
            correlated.append((obs, sd))
        else:
            values = draw_observation(obs, rng, count, relative_sd, censoring, uncertainty,
                                      (censor_models or {}).get(obs.analyte))
            if values is None:
                skipped.append(obs)
            else:
                samples[obs.analyte] = values
    if correlated:
        shared = rng.standard_normal(count)
        for obs, sd in correlated:
            z = np.sqrt(correlation)*shared + np.sqrt(1-correlation)*rng.standard_normal(count)
            sigma2 = np.log1p((sd/obs.value)**2)
            samples[obs.analyte] = np.exp(np.log(obs.value)-sigma2/2 + np.sqrt(sigma2)*z)
    return samples, skipped


def interval(values):
    finite = np.isfinite(values)
    if not finite.any():
        return {'median': np.nan, 'lower': np.nan, 'upper': np.nan, 'valid_draws': 0}
    q = np.quantile(np.asarray(values)[finite], [.025, .5, .975])
    return dict(lower=q[0], median=q[1], upper=q[2], valid_draws=int(finite.sum()))


def probability(values):
    p = float(np.mean(values))
    n = len(values)
    # Wilson interval remains nonzero at p=0 or p=1; MC precision only.
    center = (p + 1.96**2 / (2*n)) / (1 + 1.96**2/n)
    half = 1.96*np.sqrt(p*(1-p)/n + 1.96**2/(4*n*n))/(1 + 1.96**2/n)
    return {'probability': p, 'mc_se': np.sqrt(p*(1-p)/n),
            'mc_wilson_lower': center-half, 'mc_wilson_upper': center+half,
            'split_half_difference': abs(float(np.mean(values[:n//2])) - float(np.mean(values[n//2:])))}


def propagate(m, *, draws=2000, seed=42, relative_sd=0.0, uncertainty='fixed',
              censoring='exclude', profile=None, budget=10.0, assay_cost=1.0, error_correlation=0.0,
              censor_models=None, priority_method='ambiguity', followup_relative_sd=.05):
    validate_options(draws, seed, relative_sd, censoring, uncertainty)
    profile = validate_profile(profile or WHO_SCREENING)
    if not np.isfinite([budget, assay_cost]).all() or budget < 0 or assay_cost <= 0:
        raise ValueError('Budget must be nonnegative and assay cost positive.')
    if priority_method not in ('ambiguity', 'evsi'):
        raise ValueError('Choose ambiguity or evsi for assay priorities.')
    if not np.isfinite(followup_relative_sd) or followup_relative_sd <= 0:
        raise ValueError('Follow-up relative SD must be positive and finite.')
    for model in (censor_models or {}).values():
        validate_censor_model(model)
    rng = np.random.default_rng(seed)
    intervals, classes, screening, skipped, bounds, decision_inputs = [], [], [], [], [], []
    from ..core.progress import report_progress
    groups = m.observations.groupby('row', sort=True)
    for index, (row, group) in enumerate(groups):
        report_progress(95 * index / len(groups), f'Assessing sample {index + 1} of {len(groups)}')
        samples, excluded = draw_group(group, rng, draws, relative_sd, censoring, uncertainty, error_correlation, censor_models)
        for obs in excluded:
            skipped.append({'row': row, 'analyte': obs.analyte, 'status': obs.status,
                            'reason': 'No supported distribution under selected uncertainty/censoring settings'})
        eq = {a: samples[a] * CHARGES[a] / WEIGHTS[a] for a in CORE if a in samples}
        metrics = {}
        if all(a in eq for a in ('Ca', 'Mg', 'Na')):
            divisor = (eq['Ca'] + eq['Mg'])/2
            metrics['SAR'] = np.divide(eq['Na'], np.sqrt(divisor), out=np.full(draws, np.nan), where=divisor > 0)
        if all(a in eq for a in ('Ca', 'Mg', 'Na', 'K')):
            cat = sum(eq[a] for a in ('Ca', 'Mg', 'Na', 'K'))
            metrics['Na_percent'] = np.divide(100*eq['Na'], cat, out=np.full(draws, np.nan), where=cat > 0)
        if all(a in eq for a in CORE):
            an = eq['HCO3'] + eq['CO3'] + eq['Cl'] + eq['SO4']
            valid = (cat > 0) & (an > 0)
            catfrac = np.stack([eq['Ca'], eq['Mg'], eq['Na'] + eq['K']], axis=1) / np.where(cat > 0, cat, np.nan)[:, None]
            anfrac = np.stack([eq['HCO3'] + eq['CO3'], eq['SO4'], eq['Cl']], axis=1) / np.where(an > 0, an, np.nan)[:, None]
            metrics['CBE_percent'] = 100*(cat-an) / np.where(cat+an > 0, cat+an, np.nan)
            metrics.update(Piper_cation_x=catfrac[:, 2]+.5*catfrac[:, 1],
                           Piper_cation_y=np.sqrt(3)/2*catfrac[:, 1],
                           Piper_anion_x=anfrac[:, 2]+.5*anfrac[:, 1],
                           Piper_anion_y=np.sqrt(3)/2*anfrac[:, 1])
            # Diamond uses fraction (Na+K) and (Cl+SO4); unit-square rhombus.
            nafrac, strong = catfrac[:, 2], anfrac[:, 1]+anfrac[:, 2]
            metrics['Piper_diamond_x'] = .5*(nafrac+strong)
            metrics['Piper_diamond_y'] = np.sqrt(3)/2*(1-nafrac+strong)
            catcode = np.where(catfrac.max(axis=1) > .5, catfrac.argmax(axis=1), 3)
            ancode = np.where(anfrac.max(axis=1) > .5, anfrac.argmax(axis=1), 3)
            cn, anames = ['Ca', 'Mg', 'Na+K', 'mixed cation'], ['HCO3+CO3', 'SO4', 'Cl', 'mixed anion']
            labels = np.array([cn[c]+' / '+anames[a] if ok else 'Undefined' for c,a,ok in zip(catcode, ancode, valid)])
            for name in np.unique(labels):
                classes.append({'row': row, 'system': 'dominant-ion facies (>50%)', 'class': name, **probability(labels == name)})
        for name, values in metrics.items():
            intervals.append({'row': row, 'metric': name, **interval(values)})
        if 'EC' in samples and 'SAR' in metrics:
            values = pd.DataFrame({'EC_uS_cm': samples['EC'], 'SAR': metrics['SAR']})
            for system, labels in [('USSL', classify_ussl(values)['USSL_graphical_class'])]:
                for name in labels.unique():
                    classes.append({'row': row, 'system': system, 'class': name, **probability(np.asarray(labels == name))})
            if 'Na_percent' in metrics:
                values['Na_percent'] = metrics['Na_percent']
                labels = classify_wilcox(values)['Wilcox_graphical_class']
                for name in labels.unique():
                    classes.append({'row': row, 'system': 'Wilcox', 'class': name, **probability(np.asarray(labels == name))})
        for t in profile['thresholds']:
            a = t['analyte']
            observation = group[group.analyte == a]
            if len(observation):
                obs = observation.iloc[0]
                lower_bound, upper_bound = 0., 1.
                if obs.status == 'left_censored' and np.isfinite(obs.limit) and obs.limit <= t['value']:
                    upper_bound = 0.
                elif obs.status == 'right_censored' and np.isfinite(obs.limit) and obs.limit > t['value']:
                    lower_bound = 1.
                if obs.status not in ('detected', 'zero'):
                    bounds.append({'row':row, 'analyte':a, 'status':obs.status, 'limit':obs.limit,
                                   'probability_lower_bound':lower_bound, 'probability_upper_bound':upper_bound,
                                   'interpretation':'Logical bound conditional on a valid reporting inequality; no error model for the limit'})
                if a in samples and obs.status == 'detected' and obs.value > 0:
                    sd = obs.value*relative_sd if uncertainty == 'scenario' else obs.sd if uncertainty == 'laboratory' else 0.
                    if np.isfinite(sd):
                        sig2 = np.log1p((sd/obs.value)**2)
                        cv = obs.get('followup_relative_sd', np.nan)
                        cv = followup_relative_sd if not np.isfinite(cv) else cv
                        decision_inputs.append({'row':row,'analyte':a, 'log_mean':np.log(obs.value)-sig2/2,
                                                'log_sd':np.sqrt(sig2), 'threshold':t['value'],
                                                'assay_log_sd':np.sqrt(np.log1p(cv**2)), 'followup_relative_sd':cv})
            if a not in samples:
                screening.append({'row': row, 'analyte': a, 'threshold_mg_L': t['value'], 'status': 'not assessable'})
                continue
            values = samples[a]
            p = probability(values > t['value'])
            screening.append({'row': row, 'analyte': a, 'threshold_mg_L': t['value'],
                              'status': 'assessed', **interval(values), **p})
    # Keep a stable schema even when no requested analyte is assessable.
    thresholds = pd.DataFrame(screening).reindex(columns=[
        'row','analyte','threshold_mg_L','status','lower','median','upper','valid_draws',
        'probability','mc_se','mc_wilson_lower','mc_wilson_upper','split_half_difference'])
    priorities = thresholds[thresholds.status == 'assessed'].copy()
    if len(priorities):
        priorities['ambiguity'] = np.minimum(priorities.probability, 1-priorities.probability)
        priorities['relative_margin'] = abs(priorities['median']-priorities.threshold_mg_L)/priorities.threshold_mg_L
        priorities['assay_cost'] = assay_cost
        priorities['priority_score'] = priorities.ambiguity / assay_cost
        priorities['priority_method'] = priority_method
        if priority_method == 'evsi':
            decision = pd.DataFrame(decision_inputs)
            if len(decision):
                result = expected_value(decision.log_mean, decision.log_sd, decision.threshold, decision.assay_log_sd)
                for name, values in result.items():
                    decision[name] = values
                priorities = priorities.merge(decision, on=['row','analyte'], how='left')
                priorities['priority_score'] = priorities.evsi / assay_cost
            else:
                for name in ('current_risk','expected_posterior_risk','evsi','followup_relative_sd'):
                    priorities[name] = np.nan
                priorities['priority_score'] = np.nan
            priorities['decision_status'] = np.where(priorities.priority_score.notna(), 'eligible', 'unsupported current distribution; review separately')
        priorities = priorities.sort_values(['priority_score', 'relative_margin', 'row', 'analyte'], ascending=[False, True, True, True]).reset_index(drop=True)
        priorities['rank'] = np.arange(1, len(priorities)+1)
        priorities['selected_for_review'] = (priorities['rank']*assay_cost <= budget) & (priorities.priority_score > 0)
        priorities['margin_baseline_rank'] = priorities.relative_margin.rank(method='first').astype(int)
        priorities['exceedance_baseline_rank'] = priorities.probability.rank(method='first', ascending=False).astype(int)
    notes = list(m.warnings)
    notes.extend([
        f'Positive lognormal observations use shared log-error correlation {error_correlation:g}; zero gives independence. This is an explicit covariance scenario, not an estimated laboratory correlation. Censor draws are independent.',
        'Intervals are conditional 95% Monte Carlo intervals. Wilson bounds describe simulation precision, not confidence in the uncertainty assumptions.',
        ('Assay priorities rank threshold ambiguity per equal assay cost; this is a review heuristic, not value of information or a safety ranking.'
         if priority_method == 'ambiguity' else
         'Assay priorities use expected reduction in unit binary decision loss under a normal log-concentration model and independent follow-up log-assay error. Equal assay costs, stable chemistry, additive loss and no information sharing across candidates are assumed. Censored current distributions are ineligible. This is not a health-risk ranking.'),
        'Not-assessable thresholds are exported separately and must be reviewed; they cannot receive a probability-based rank.',
        profile.get('purpose', 'Screening only; verify suitability of the chosen threshold profile.'),
        'Piper uses eight measured major ions. Missing carbonate is not assumed zero; major-ion CBE omits nitrate and trace species.',
        'USSL/Wilcox probabilities retain the existing historical graphical boundaries; EC must refer to 25 C.',
    ])
    notes.append({'fixed': 'Detected values are held fixed: no measurement-uncertainty model.',
                  'scenario': f'Sensitivity scenario: relative SD = {relative_sd:.1%}; these are not supplied laboratory error estimates.',
                  'laboratory': 'Measurement scenario: supplied SDs moment-match lognormal marginals with the selected log-error correlation; detected cells without SD are excluded.'}[uncertainty])
    if censoring != 'exclude':
        notes.append({'uniform':'Censoring scenario: uniform(0, limit).',
                      'half_limit':'Censoring sensitivity: fixed limit/2 substitution; no within-limit uncertainty.',
                      'lognormal':'Censoring model: supplied lognormal distribution truncated below each limit. Parameters are fixed; training-set parameter uncertainty and cross-ion censoring dependence are not included. Missing model/limit remains unassessed.'}[censoring])
    return {'metric_intervals': pd.DataFrame(intervals), 'class_probabilities': pd.DataFrame(classes),
            'threshold_probabilities': thresholds, 'assay_priorities': priorities,
            'excluded_from_propagation': pd.DataFrame(skipped), 'censoring_probability_bounds': pd.DataFrame(bounds)}, notes


def compare_scenarios(m, *, draws=2000, seed=42, relative_sd=.05, profile=None, error_correlation=0.0):
    """Display alternatives without assigning probabilities to modelling choices."""
    outputs, class_outputs = [], []
    cases = [('fixed/exclude', 'fixed', 0, 'exclude'),
             ('relative-SD/exclude', 'scenario', relative_sd, 'exclude'),
             ('relative-SD/uniform', 'scenario', relative_sd, 'uniform'),
             ('relative-SD/half-limit', 'scenario', relative_sd, 'half_limit')]
    from ..core.progress import progress_stage
    for index, (name, mode, cv, method) in enumerate(cases):
        with progress_stage(95 * index / len(cases), 95 * (index + 1) / len(cases), 'Comparing uncertainty scenarios'):
            tables, _ = propagate(m, draws=draws, seed=seed, relative_sd=cv, uncertainty=mode,
                                  censoring=method, profile=profile, error_correlation=error_correlation)
        outputs.append(tables['threshold_probabilities'].assign(scenario=name))
        cp = tables['class_probabilities']
        if not cp.empty:
            best = cp.sort_values('probability', ascending=False).drop_duplicates(['row', 'system'])
            class_outputs.append(best.assign(scenario=name))
    all_thresholds = pd.concat(outputs, ignore_index=True)
    summaries = []
    for (row, analyte), group in all_thresholds.groupby(['row', 'analyte'], sort=False):
        p = group.get('probability', pd.Series(dtype=float)).dropna()
        state = 'insufficient information'
        if len(p) == len(cases):
            state = 'stable below (P <= 0.05)' if p.max() <= .05 else 'stable above (P >= 0.95)' if p.min() >= .95 else 'scenario-dependent or ambiguous'
        summaries.append({'row': row, 'analyte': analyte, 'assessable_scenarios': len(p),
                          'minimum_probability': p.min(), 'maximum_probability': p.max(), 'conclusion': state})
    return {'scenario_conclusions': pd.DataFrame(summaries), 'scenario_thresholds': all_thresholds,
            'scenario_dominant_classes': pd.concat(class_outputs, ignore_index=True) if class_outputs else pd.DataFrame()}, [
                'Four sensitivity alternatives are compared separately; no probability or weight is assigned to the modelling choices.',
                'Stable means all four scenarios are assessable and all probabilities are at most 0.05 or at least 0.95; this is a display rule, not a regulatory rule.',
                'Uniform and half-limit assumptions cannot resolve non-detects whose limits are unknown.']
