from datetime import timedelta
import numpy as np
from backend.database import query
from backend.matching import GRID_IDS, POLLUTANTS, WEATHER_FIELDS, LABEL_FIELDS


def list_batches():
    rows = query('''SELECT forecast_start_time,valid_date,count(*) AS dimension_count
        FROM pollutant_grid_daily_forecast GROUP BY forecast_start_time,valid_date
        ORDER BY forecast_start_time DESC,valid_date''')
    batches = {}
    for row in rows:
        batch = batches.setdefault(row['forecast_start_time'], {'forecast_start_time':row['forecast_start_time'], 'dates':[], 'incomplete_dates':[]})
        batch['dates' if row['dimension_count'] == 36 else 'incomplete_dates'].append(row['valid_date'])
    result = []
    for batch in batches.values():
        if not batch['dates']:
            continue
        first = batch['dates'][0]
        # Display actual first seven calendar dates, never jump gaps or splice batches.
        batch['dates'] = [day for day in batch['dates'] if day < first+timedelta(days=7)]
        batch['has_full_seven_days'] = len(batch['dates']) == 7
        result.append(batch)
    return result


def pollutant_arrays(rows):
    days = {}
    for row in rows:
        values = days.setdefault(row['valid_date'], np.full((9,4),np.nan))
        values[GRID_IDS.index(row['station_grid_id']),POLLUTANTS.index(row['pollutant_name'])] = row['concentration']
    return {day:values for day,values in days.items() if np.isfinite(values).all() and (values >= 0).all()}


def load_inputs(batch):
    current = pollutant_arrays(query('SELECT * FROM pollutant_grid_daily_forecast WHERE forecast_start_time=%s',(batch,)))
    observed = pollutant_arrays(query('SELECT * FROM pollutant_grid_daily_observation'))
    weather, labels = {}, {}
    for row in query('SELECT * FROM meteorology_grid_daily'):
        values = weather.setdefault(row['valid_date'],np.full((9,6),np.nan))
        values[GRID_IDS.index(row['meteorology_grid_id'])] = [row[field] for field in WEATHER_FIELDS]
        if row['meteorology_grid_id'] == 'C':
            labels[row['valid_date']] = [row[field] for field in LABEL_FIELDS]
    weather = {day:values for day,values in weather.items() if np.isfinite(values).all() and day in labels}
    return current, observed, weather, labels


def historical_residuals(batch, current_dates, historical_start):
    historical_batch = batch - (current_dates[0]-historical_start)
    rows = query('''SELECT current.station_id,station.station_name,current.pollutant_name,
        current.valid_date,current.forecast_value AS current_forecast,
        observed.valid_date AS history_date,observed.observed_value AS historical_observed,
        historical.forecast_value AS historical_forecast,
        observed.observed_value-historical.forecast_value AS residual
        FROM station_daily_forecast current JOIN station USING(station_id)
        JOIN station_daily_observation observed ON observed.station_id=current.station_id
          AND observed.pollutant_name=current.pollutant_name AND observed.valid_date=current.valid_date-%s
        JOIN station_daily_forecast historical ON historical.station_id=current.station_id
          AND historical.pollutant_name=current.pollutant_name AND historical.valid_date=observed.valid_date
          AND historical.forecast_start_time=%s
        WHERE current.forecast_start_time=%s AND current.valid_date BETWEEN %s AND %s
        ORDER BY current.valid_date,current.station_id,current.pollutant_name''',
        ((current_dates[0]-historical_start).days,historical_batch,batch,current_dates[0],current_dates[-1]))
    return {'historical_forecast_start_time':historical_batch if rows else None, 'rows':rows,
            'is_adjustment_enabled':False,
            'reason':'仅展示2025同源新模型、对应预报日序的历史误差；未通过独立回放，未生成定量订正。' if rows else '没有覆盖相同预报日序的历史预测，不生成误差或订正。',
            'comparability_assumption':'固定2025同源新模型；现有表缺少模型与后处理版本字段，不能据此认证正式业务可比性。'}
