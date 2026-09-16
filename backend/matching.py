"""V2.1 deterministic scoring. Inputs are statistical concentrations, not AQI."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
import numpy as np

GRID_IDS = ('NW', 'N', 'NE', 'W', 'C', 'E', 'SW', 'S', 'SE')
POLLUTANTS = ('PM2.5', 'PM10', 'NO2', 'O3')
THRESHOLDS = np.array([60., 120., 80., 160.])
BREAKPOINTS = ([0,35,60,115,150,250,350,500], [0,50,120,250,350,420,500,600],
               [0,40,80,180,280,565,750,940], [0,100,160,215,265,800])
INDEX_NODES = [0,50,100,150,200,300,400,500]
WEATHER_FIELDS = ('temperature','relative_humidity','eastward_wind','northward_wind','air_pressure','pressure_gradient')
LABEL_FIELDS = ('temperature_level','humidity_level','wind_speed_level','wind_direction','pressure_level','pressure_gradient_level')
WEATHER_WEIGHTS = np.array([.05,.1,.05,.1,.4,.1,.05,.1,.05])[:,None] * np.array([.15,.2,.175,.175,.15,.15])
LABEL_ORDERS = (('偏冷','正常','偏暖'),('低湿','中湿','高湿'),('弱风','中等风','较强风'),
                ('北','东北','东','东南','南','西南','西','西北'),('偏低','正常','偏高'),('弱','中','强'))


def evaluate_concentration(value, pollutant_index):
    if not np.isfinite(value) or value < 0:
        raise ValueError('污染物浓度存在无效值')
    concentration = int(Decimal(str(float(value))).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN))
    nodes = BREAKPOINTS[pollutant_index]
    is_above = concentration > nodes[-1]
    index = int(np.ceil(np.interp(concentration, nodes, INDEX_NODES[:len(nodes)])))
    band = int(np.searchsorted([50,100,150,200,300], index, side='left'))
    return {'evaluation_concentration': concentration, 'air_quality_subindex': index,
            'band': band, 'is_above_index_table': is_above,
            'is_above_threshold': concentration > THRESHOLDS[pollutant_index]}


def daily_labels(values):
    return [[[evaluate_concentration(value, pollutant) for pollutant, value in enumerate(cell)]
             for cell in day] for day in values]


def process_features(values, change_thresholds):
    values = np.asarray(values, dtype=float)
    if values.ndim != 3 or values.shape[1:] != (9,4) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('污染物必须完整覆盖每一天的九格四项')
    differences = np.diff(values, axis=0)
    directions = np.where(differences > change_thresholds, 1, np.where(differences < -change_thresholds, -1, 0))
    labels = daily_labels(values)
    features = []
    for grid_index, grid_id in enumerate(GRID_IDS):
        for pollutant_index, pollutant in enumerate(POLLUTANTS):
            series = values[:, grid_index, pollutant_index]
            sequence = directions[:, grid_index, pollutant_index].tolist()
            compressed = []
            for direction in sequence:
                if direction and (not compressed or compressed[-1] != direction):
                    compressed.append(direction)
            pattern = {(): '平稳', (1,): '上升', (-1,): '下降', (1,-1): '先升后降', (-1,1): '先降后升'}.get(tuple(compressed), '多次波动')
            if len(series) == 1:
                pattern = '单日'
            exceedances = [day[grid_index][pollutant_index]['is_above_threshold'] for day in labels]
            longest_run = current_run = 0
            for is_above in exceedances:
                current_run = current_run + 1 if is_above else 0
                longest_run = max(longest_run, current_run)
            positions = (np.flatnonzero(series == series.max()) + 1).tolist()
            features.append({'grid_id': grid_id, 'pollutant_name': pollutant,
                             'directions': [ {-1:'DOWN',0:'STABLE',1:'UP'}[x] for x in sequence],
                             'pattern': pattern, 'has_stable_stage': 0 in sequence,
                             'peak_positions': positions, 'peak_concentration': float(series.max()),
                             'exceedance_days': int(sum(exceedances)), 'longest_run': longest_run})
    return features, directions, labels


def compare_pollutants(current, historical, standard_deviations, change_thresholds):
    current = np.asarray(current, dtype=float)
    historical = np.asarray(historical, dtype=float)
    if current.shape != historical.shape or not 1 <= len(current) <= 7:
        raise ValueError('当前与历史窗口必须等长且为1—7天')
    current_features, current_directions, current_labels = process_features(current, change_thresholds)
    historical_features, historical_directions, historical_labels = process_features(historical, change_thresholds)
    standard_deviations = np.asarray(standard_deviations, dtype=float)
    valid_dimensions = np.isfinite(standard_deviations) & (standard_deviations >= 1e-6)
    if standard_deviations.shape != (9,4) or (valid_dimensions.mean(axis=0) < .8).any():
        raise ValueError('每种污染物至少需要80%的标准差有效格日维度')
    distance = np.sqrt(np.mean(((current - historical)[:, valid_dimensions] / standard_deviations[valid_dimensions]) ** 2))
    numeric_score = float(100 / (1 + distance))
    band_differences = np.abs(np.array([[[v['band'] for v in cell] for cell in day] for day in current_labels]) -
                              np.array([[[v['band'] for v in cell] for cell in day] for day in historical_labels]))
    daily_band_score = float(100 * np.maximum(0, 1 - band_differences * .5).mean())
    transition_score = process_score = None
    if len(current) == 1:
        coarse_score = .875 * numeric_score + .125 * daily_band_score
        fine_score = numeric_score
    else:
        direction_scores = 100 * (1 - np.abs(current_directions - historical_directions) / 2).mean(axis=0)
        transition_score = float(direction_scores.mean())
        process_scores = []
        for index, (left, right) in enumerate(zip(current_features, historical_features)):
            peak_distance = min(abs(a-b) for a in left['peak_positions'] for b in right['peak_positions'])
            peak_score = 100 * (1 - peak_distance / (len(current)-1))
            days_score = 100 * (1 - abs(left['exceedance_days'] - right['exceedance_days']) / len(current))
            run_score = 100 * (1 - abs(left['longest_run'] - right['longest_run']) / len(current))
            process_scores.append(.4 * direction_scores.flat[index] + .2 * (peak_score + days_score + run_score))
        process_score = float(np.mean(process_scores))
        coarse_score = .7 * numeric_score + .1 * daily_band_score + .2 * transition_score
        fine_score = .7 * numeric_score + .3 * process_score
    return {'numeric_score': numeric_score, 'daily_band_score': daily_band_score,
            'transition_score': transition_score, 'process_score': process_score,
            'coarse_pollutant_score': coarse_score, 'fine_pollutant_score': fine_score,
            'current_features': current_features, 'historical_features': historical_features,
            'current_labels': current_labels, 'historical_labels': historical_labels}


def validate_window(start, end, available_dates):
    length = (end - start).days + 1
    if not 1 <= length <= 7:
        raise ValueError('请选择连续1—7天')
    dates = [start + timedelta(days=offset) for offset in range(length)]
    missing = [str(day) for day in dates if day not in available_dates]
    if missing:
        raise ValueError('所选批次缺少完整数据：' + '、'.join(missing))
    return dates


def compare_weather(current, historical, current_labels, historical_labels, standard_deviations):
    current, historical = np.asarray(current), np.asarray(historical)
    if current.shape != historical.shape or not np.isfinite(current).all() or not np.isfinite(historical).all():
        raise ValueError('气象九格六项数值缺失')
    daily_scores = []
    for left, right in zip(current_labels, historical_labels):
        scores = []
        for index, (a,b,order) in enumerate(zip(left,right,LABEL_ORDERS)):
            if index == 3 and (a in ('静风','风向分散') or b in ('静风','风向分散')):
                continue
            if a not in order or b not in order:
                raise ValueError('气象中心格必需日标签无效')
            difference = abs(order.index(a) - order.index(b))
            if index == 3:
                difference = min(difference,8-difference)
            scores.append(max(0,1-.5*difference))
        if len(scores) < 5:
            raise ValueError('气象中心格缺少必需日标签')
        daily_scores.append(np.mean(scores))
    standard_deviations = np.asarray(standard_deviations)
    valid = np.isfinite(standard_deviations) & (standard_deviations >= 1e-6)
    if not valid.any():
        raise ValueError('气象标准差基准全部退化')
    squared = ((current - historical)[:, valid] / standard_deviations[valid]) ** 2
    distance = np.sqrt(np.sum(squared * WEATHER_WEIGHTS[valid]) / (len(current) * WEATHER_WEIGHTS[valid].sum()))
    return {'label_score': float(100*np.mean(daily_scores)), 'numeric_score': float(100/(1+distance))}


def select_nonoverlapping(ranked_candidates, length, limit=50):
    occupied, selected = set(), []
    for candidate in ranked_candidates:
        dates = {candidate['history_start_date'] + timedelta(days=offset) for offset in range(length)}
        if not dates & occupied:
            selected.append(candidate)
            occupied.update(dates)
            if len(selected) == limit:
                break
    return selected


def finalize_candidates(candidates):
    successful = []
    for candidate in candidates:
        candidate.pop('final_rank',None)
        image_score = candidate.get('image_score')
        if image_score is not None and np.isfinite(image_score) and 0 <= image_score <= 100:
            candidate['final_score'] = .6*candidate['fine_pollutant_score'] + .2*candidate['meteorology_score'] + .2*image_score
            successful.append(candidate)
    if len(successful) < 3:
        return []
    successful.sort(key=lambda item:(-item['final_score'],-item['fine_score'],-item['coarse_score'],item['history_start_date']))
    for rank,candidate in enumerate(successful,1):
        candidate['final_rank'] = rank
    return successful


def calibrate_changes(observations, first_date):
    pairs = [(day, np.abs(observations[day+timedelta(days=1)]-values)) for day, values in observations.items()
             if day+timedelta(days=1) in observations]
    def day_number(day):
        return date(2000, day.month, day.day).timetuple().tm_yday
    def season(day):
        return (day.month % 12) // 3
    target = day_number(first_date)
    nearby = [values for day, values in pairs if min(abs(day_number(day)-target),366-abs(day_number(day)-target)) <= 30]
    seasonal = [values for day, values in pairs if season(day) == season(first_date)]
    for samples, minimum, source in [(nearby,60,'DAY_OF_YEAR'),(seasonal,60,'SEASON'),([v for _,v in pairs],120,'YEAR')]:
        if len(samples) >= minimum:
            return np.maximum(.05*THRESHOLDS,np.quantile(samples,.2,axis=0)), {'source':source,'sample_count':len(samples)}
    return np.tile(.05*THRESHOLDS,(9,1)), {'source':'INITIAL_FALLBACK','sample_count':len(pairs)}


def rank_windows(current, current_weather, current_labels, observations, weather, weather_labels, start_date, allowed_field_dates, task_date):
    """Fixed-2025 dataset mode: shared full-library baseline, explicitly not historical replay."""
    if len(observations) < 2 or len(weather) < 2:
        raise ValueError('历史样本不足，无法建立标准差基准')
    pollutant_deviations = np.std(list(observations.values()), axis=0, ddof=1)
    weather_deviations = np.std(list(weather.values()), axis=0, ddof=1)
    change_thresholds, change_metadata = calibrate_changes(observations, start_date)
    candidates, skipped = [], {'missing_pollutants':0,'missing_weather_or_fields':0,'invalid_features':0}
    length = len(current)
    for historical_start in sorted(observations):
        historical_dates = [historical_start+timedelta(days=offset) for offset in range(length)]
        if historical_dates[-1] >= min(start_date,task_date) or historical_start < date(2023,1,1):
            continue
        if any(day not in observations for day in historical_dates):
            skipped['missing_pollutants'] += 1
            continue
        if any(day not in weather or day not in allowed_field_dates for day in historical_dates):
            skipped['missing_weather_or_fields'] += 1
            continue
        try:
            historical = np.stack([observations[day] for day in historical_dates])
            historical_weather = np.stack([weather[day] for day in historical_dates])
            pollutant_scores = compare_pollutants(current, historical, pollutant_deviations, change_thresholds)
            meteorology_scores = compare_weather(current_weather,historical_weather,current_labels,
                                                [weather_labels[day] for day in historical_dates],weather_deviations)
        except ValueError:
            skipped['invalid_features'] += 1
            continue
        candidates.append({'history_start_date':historical_start, 'history_end_date':historical_dates[-1],
                           **pollutant_scores, 'meteorology_label_score':meteorology_scores['label_score'],
                           'meteorology_score':meteorology_scores['numeric_score'],
                           'coarse_score':.6*pollutant_scores['coarse_pollutant_score']+.4*meteorology_scores['label_score'],
                           'fine_score':.6*pollutant_scores['fine_pollutant_score']+.4*meteorology_scores['numeric_score'],
                           'valid_ratio':1.0, 'historical_values':historical.tolist(),
                           'historical_weather':historical_weather.tolist(),
                           'historical_weather_labels':[weather_labels[day] for day in historical_dates],
                           'is_low_similarity':pollutant_scores['coarse_pollutant_score']<50 or meteorology_scores['label_score']<40})
    candidates.sort(key=lambda c:(-c['coarse_score'],-c['coarse_pollutant_score'],-c['meteorology_label_score'],-c['valid_ratio'],c['history_start_date']))
    selected = select_nonoverlapping(candidates,length)
    for index,candidate in enumerate(selected,1):
        candidate['coarse_rank'] = index
    selected.sort(key=lambda c:(-c['fine_score'],-c['coarse_score'],-c['valid_ratio'],c['history_start_date']))
    for index,candidate in enumerate(selected,1):
        candidate['fine_rank'] = index
    baseline = {'mode':'FIXED_2025_TEST','pollutant_sample_count':len(observations),'weather_sample_count':len(weather),
                'pollutant_standard_deviations':pollutant_deviations.tolist(),
                'weather_standard_deviations':weather_deviations.tolist(),
                'change_thresholds':change_thresholds.tolist(),'change_baseline':change_metadata,
                'pollutant_mean':np.mean(list(observations.values()),axis=0).tolist(),
                'weather_mean':np.mean(list(weather.values()),axis=0).tolist(),
                'qualified_window_count':len(candidates),'skipped':skipped}
    return selected, baseline
