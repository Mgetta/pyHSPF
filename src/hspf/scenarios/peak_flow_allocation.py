"""Peak Flow Allocation scenario construction and analysis."""

from pathlib import Path
import json
import os
import shutil
import warnings

import numpy as np
import pandas as pd

from hspf import hbn
from hspf.hspfModel import check_run_status, run_batch_staged, run_uci
from hspf.reports.timeseries import independent_peaks
from hspf.uci import UCI, remove_routing_reaches, set_schematic_area, setup_binaryinfo


def scenario_name(reach_id, outlet_reach):
    """Return the stable name used for a reach-removal scenario."""
    return f'RCH{int(reach_id)}_to_RCH{int(outlet_reach)}'


def make_baseline_uci(uci, outlet_reach, remove_routing=False,
                      trim_output=True):
    """Apply Peak Flow Allocation baseline edits to a loaded UCI."""
    if outlet_reach not in uci.valid_opnids['RCHRES']:
        raise ValueError(f'Outlet RCHRES {outlet_reach} is not in OPN SEQUENCE')
    drainage_area = uci.network.drainage_area([outlet_reach])
    upstream = set(uci.network._upstream(outlet_reach))
    if trim_output:
        setup_binaryinfo(
            uci, default_output=6, reach_ids=[outlet_reach],
            constituents=['Q'], reach_output=3)
    else:
        uci.update_table(
            3, 'RCHRES', 'BINARY-INFO', 0, opnids=[outlet_reach],
            columns='HYDRPR', operator='set')
    if remove_routing:
        routing = [reach for reach in uci.network.routing_reaches
                   if reach in upstream]
        remove_routing_reaches(uci, routing)
        new_area = uci.network.drainage_area([outlet_reach])
        new_upstream = set(uci.network._upstream(outlet_reach))
        if not np.isclose(new_area, drainage_area) or new_upstream != upstream - set(routing):
            raise ValueError('Removing routing reaches changed the outlet watershed')
    return uci


def set_reach_precipitation_factor(uci, reach_ids, factor=0.0):
    """Set the EXT SOURCES factor for precipitation supplied to reaches."""
    reach_ids = {int(reach_id) for reach_id in reach_ids}
    sources = uci.table('EXT SOURCES', drop_comments=False)
    selected = (
        (sources['TVOL'] == 'RCHRES') &
        sources['TOPFST'].isin(reach_ids) &
        (sources['TMEMN'] == 'PREC'))
    sources.loc[selected, 'MFACTOR'] = float(factor)
    uci.replace_table(sources, 'EXT SOURCES')
    return int(selected.sum())


def make_scenario_uci(baseline_uci_path, reach_id, outlet_reach):
    """Load a baseline UCI and remove one reach's local contribution."""
    baseline_uci_path = Path(baseline_uci_path)
    uci = UCI(baseline_uci_path, infer_metzones=False)
    if reach_id not in uci.valid_opnids['RCHRES']:
        raise ValueError(f'RCHRES {reach_id} is not in OPN SEQUENCE')
    set_schematic_area(uci, [reach_id], 0.0)
    set_reach_precipitation_factor(uci, [reach_id], 0.0)
    uci.update_bino(scenario_name(reach_id, outlet_reach))
    return uci


def daily_rovol(hbn_paths, reach_id):
    """Read daily ROVOL for one reach in acre-feet per day."""
    hbns = hbn.hbnInterface(hbn_paths)
    series = hbn.get_simulated_flow(hbns, 'daily', [reach_id], unit='acrft')
    series.name = 'ROVOL_acft'
    return series


def write_sorted_flow_csv(series, path, instructions=True):
    """Write daily flows from highest to lowest with optional instructions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flows = series.dropna().sort_values(ascending=False).rename('ROVOL_acft')
    frame = flows.rename_axis('Date').reset_index()
    frame['Date'] = pd.to_datetime(frame['Date']).dt.strftime('%Y-%m-%d')
    with path.open('w', newline='') as stream:
        if instructions:
            stream.write('# Daily outlet ROVOL sorted from highest to lowest.\n')
            stream.write('# Review suggested independent events, then confirm the final event dates.\n')
        frame.to_csv(stream, index=False)
    return path


def event_totals(series, event_dates):
    """Return flow values at selected dates and their total."""
    dates = pd.DatetimeIndex(pd.to_datetime(event_dates))
    missing = dates.difference(series.index)
    if len(missing):
        values = ', '.join(date.strftime('%Y-%m-%d') for date in missing)
        raise ValueError(f'Event dates are missing from the time series: {values}')
    selected = series.reindex(dates).astype(float)
    if selected.isna().any():
        values = ', '.join(date.strftime('%Y-%m-%d') for date in selected.index[selected.isna()])
        raise ValueError(f'Event dates have missing values: {values}')
    return selected, float(selected.sum())


def allocation(baseline_total, scenario_total, avg_area, reach_area):
    """Calculate area-normalized peak-flow allocation."""
    if reach_area <= 0:
        raise ValueError('reach_area must be positive')
    return (baseline_total - scenario_total) * avg_area / reach_area


def analyze(results_csv):
    """Recompute allocation metrics and ranking from a PFA results CSV."""
    results = pd.read_csv(results_csv, comment='#')
    required = {'scenario', 'reach_area', 'total_acft', 'avg_area'}
    missing = required.difference(results.columns)
    if missing:
        raise ValueError(f"Results CSV is missing columns: {', '.join(sorted(missing))}")
    baseline_rows = results.loc[results['scenario'].astype(str).str.lower() == 'baseline']
    if baseline_rows.empty:
        if 'baseline_total_acft' not in results.columns:
            raise ValueError('Results CSV does not contain a baseline row or total')
        baseline_total = pd.to_numeric(results['baseline_total_acft'], errors='coerce')
    else:
        baseline_total = pd.Series(
            float(baseline_rows.iloc[0]['total_acft']), index=results.index)
    results['baseline_total_acft'] = baseline_total
    results['total_acft'] = pd.to_numeric(results['total_acft'], errors='coerce')
    results['reach_area'] = pd.to_numeric(results['reach_area'], errors='coerce')
    results['avg_area'] = pd.to_numeric(results['avg_area'], errors='coerce')
    results['delta_acft'] = results['baseline_total_acft'] - results['total_acft']
    valid_area = results['reach_area'] > 0
    results['allocation'] = np.where(
        valid_area,
        results['delta_acft'] * results['avg_area'] / results['reach_area'],
        np.nan)
    results['allocation_baseline_ratio'] = np.where(
        results['baseline_total_acft'] != 0,
        results['allocation'] / results['baseline_total_acft'],
        np.nan)
    results['rank'] = results['allocation'].rank(method='min', ascending=False)
    results.loc[results['scenario'].astype(str).str.lower() == 'baseline', 'rank'] = np.nan
    return results


class PeakFlowAllocation:
    """Manage a resumable Peak Flow Allocation analysis directory."""

    def __init__(self, pfa_dir, outlet_reach):
        self.pfa_dir = Path(pfa_dir).resolve()
        self.config_path = self.pfa_dir / 'pfa_config.json'
        if not self.config_path.exists():
            raise FileNotFoundError(f'PFA configuration not found: {self.config_path}')
        self.config = json.loads(self.config_path.read_text())
        configured_outlet = int(self.config['outlet_reach'])
        if int(outlet_reach) != configured_outlet:
            raise ValueError(
                f'Configured outlet is {configured_outlet}, not {outlet_reach}')
        self.outlet_reach = configured_outlet
        self.baseline_dir = self.pfa_dir / 'baseline'
        self.ucis_dir = self.pfa_dir / 'ucis'
        self.scenarios_dir = self.pfa_dir / 'scenarios'
        self.output_dir = self.pfa_dir / 'output'
        self.baseline_uci_path = self.pfa_dir / self.config['baseline_uci']

    @classmethod
    def setup(cls, uci_file, outlet_reach, remove_routing_reaches=False,
              trim_output=True, overwrite=False):
        """Create a PFA workspace and its modified baseline UCI."""
        uci_file = Path(uci_file).resolve()
        if not uci_file.exists():
            raise FileNotFoundError(uci_file)
        pfa_dir = uci_file.parent.parent / 'scenarios' / 'peak_flow_allocation'
        if remove_routing_reaches:
            warnings.warn(
                'Routing-reach removal is experimental and caused an HSPF '
                'arithmetic overflow during NFCrow integration testing; '
                'validate the baseline run before continuing.')
        config_path = pfa_dir / 'pfa_config.json'
        if config_path.exists() and not overwrite:
            raise FileExistsError(
                f'PFA workspace already exists: {pfa_dir}. Use overwrite=True to refresh it.')
        for folder in ['baseline', 'ucis', 'scenarios', 'output']:
            (pfa_dir / folder).mkdir(parents=True, exist_ok=True)

        staged_uci_path = pfa_dir / uci_file.name
        shutil.copy2(uci_file, staged_uci_path)
        source = UCI(uci_file, infer_metzones=False)
        staged_wdms = []
        for source_wdm in source.wdm_paths:
            source_wdm = source_wdm.resolve()
            if not source_wdm.exists():
                raise FileNotFoundError(f'UCI WDM input does not exist: {source_wdm}')
            staged_wdm = pfa_dir / source_wdm.name
            shutil.copy2(source_wdm, staged_wdm)
            staged_wdms.append(staged_wdm)

        model = UCI(staged_uci_path, infer_metzones=False)
        files = model.table('FILES', drop_comments=False)
        staged_types = files['FILENAME'].str.lower().str.endswith(
            ('.wdm', '.hbn', '.ech', '.out'))
        files.loc[staged_types, 'FILENAME'] = files.loc[
            staged_types, 'FILENAME'].map(lambda value: Path(value).name)
        model.replace_table(files, 'FILES')
        original_upstream = model.network._upstream(int(outlet_reach))
        original_routing = [
            reach for reach in model.network.routing_reaches
            if reach in original_upstream]
        make_baseline_uci(
            model, int(outlet_reach), remove_routing=remove_routing_reaches,
            trim_output=trim_output)
        baseline_name = f'baseline_RCH{int(outlet_reach)}.uci'
        model.update_bino(Path(baseline_name).stem)
        baseline_uci = pfa_dir / 'baseline' / baseline_name
        model.write(staged_uci_path)
        model.write(baseline_uci)
        shutil.copy2(baseline_uci, pfa_dir / 'ucis' / baseline_name)
        for staged_wdm in staged_wdms:
            shutil.copy2(staged_wdm, pfa_dir / 'baseline' / staged_wdm.name)

        upstream = model.network._upstream(int(outlet_reach))
        config = {
            'source_uci': str(uci_file),
            'staged_uci': staged_uci_path.name,
            'baseline_uci': baseline_uci.relative_to(pfa_dir).as_posix(),
            'outlet_reach': int(outlet_reach),
            'remove_routing_reaches': bool(remove_routing_reaches),
            'trim_output': bool(trim_output),
            'wdm_files': [path.name for path in staged_wdms],
            'upstream_reaches': [int(reach) for reach in upstream],
            'routing_reaches': [int(reach) for reach in original_routing],
            'event_dates': [],
            'scenario_order': [],
        }
        cls._write_json(config_path, config)
        return cls(pfa_dir, outlet_reach)

    @staticmethod
    def _write_json(path, data):
        path = Path(path)
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(data, indent=2) + '\n')
        temporary.replace(path)

    def _save_config(self):
        self._write_json(self.config_path, self.config)

    @property
    def baseline_timeseries_path(self):
        return self.output_dir / f'baseline_RCH{self.outlet_reach}_daily_ROVOL_timeseries.csv'

    @property
    def results_path(self):
        return self.output_dir / f'peak_flow_allocation_RCH{self.outlet_reach}.csv'

    def _baseline_series(self):
        if not self.baseline_timeseries_path.exists():
            raise FileNotFoundError(
                'Baseline time series is unavailable; run run_baseline() first')
        frame = pd.read_csv(self.baseline_timeseries_path, parse_dates=['Date'])
        return frame.set_index('Date')['ROVOL_acft']

    def _analysis_reaches(self):
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        upstream = set(model.network._upstream(self.outlet_reach))
        routing = set(model.network.routing_reaches)
        return [reach for reach in model.valid_opnids['RCHRES']
                if reach in upstream and reach not in routing]

    def _average_area(self):
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        reaches = self._analysis_reaches()
        return float(np.mean([
            model.network.subwatershed_area(reach) for reach in reaches]))

    def run_baseline(self):
        """Run the baseline, validate it, and save its daily outlet flow."""
        for name in self.config['wdm_files']:
            source = self.pfa_dir / name
            target = self.baseline_dir / name
            if not target.exists():
                shutil.copy2(source, target)
        completed = run_uci(self.baseline_uci_path, cwd=self.baseline_dir)
        status = check_run_status(self.baseline_uci_path)
        status['returncode'] = getattr(completed, 'returncode', 0)
        status['ok'] = status['ok'] and status['returncode'] == 0
        if not status['ok']:
            print('\n'.join(status['errors']))
            print(f"Baseline run files retained in {self.baseline_dir}")
            return status
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        series = daily_rovol(model.hbn_paths, self.outlet_reach)
        timeseries = series.rename_axis('Date').rename('ROVOL_acft').reset_index()
        timeseries.to_csv(self.baseline_timeseries_path, index=False)
        sorted_path = self.output_dir / f'baseline_RCH{self.outlet_reach}_daily_ROVOL.csv'
        write_sorted_flow_csv(series, sorted_path)
        if hasattr(os, 'startfile'):
            os.startfile(sorted_path)
        status['flow_csv'] = sorted_path
        status['timeseries_csv'] = self.baseline_timeseries_path
        return status

    def suggest_peak_events(self, n=10, trough_ratio=0.75,
                            min_separation_days=None):
        """Save and display the largest independent baseline peak events."""
        series = self._baseline_series()
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        drainage_area_sqmi = model.network.drainage_area([self.outlet_reach]) / 640
        suggestions = independent_peaks(
            series, n=n + 5, drainage_area_sqmi=drainage_area_sqmi,
            min_separation_days=min_separation_days,
            trough_ratio=trough_ratio)
        output = self.output_dir / f'suggested_peak_events_RCH{self.outlet_reach}.csv'
        suggestions.to_csv(output, index=False)
        print(suggestions.to_string(index=False))
        return suggestions

    def set_peak_events(self, dates):
        """Validate and persist the modeler's final peak-event dates."""
        series = self._baseline_series()
        event_dates = pd.DatetimeIndex(pd.to_datetime(dates))
        if event_dates.has_duplicates:
            raise ValueError('Peak event dates must be unique')
        values, total = event_totals(series, event_dates)
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        separation = int(np.ceil(
            5 + np.log(model.network.drainage_area([self.outlet_reach]) / 640)))
        for index, first in enumerate(event_dates):
            for second in event_dates[index + 1:]:
                left, right = sorted((first, second))
                trough = series.loc[left:right].iloc[1:-1].min()
                lower = min(series.loc[first], series.loc[second])
                gap = abs((first - second).days)
                if gap < separation or pd.isna(trough) or trough >= 0.75 * lower:
                    warnings.warn(
                        f'{first.date()} and {second.date()} do not satisfy '
                        'the default USWRC independence criteria')
        for date in event_dates:
            threshold = 0.75 * series.loc[date]
            before = series.loc[:date]
            after = series.loc[date:]
            prior_crossings = before.index[before <= threshold]
            later_crossings = after.index[after <= threshold]
            start = prior_crossings[-1] if len(prior_crossings) else series.index[0]
            end = later_crossings[0] if len(later_crossings) else series.index[-1]
            event = series.loc[start:end]
            maximum_date = event.idxmax()
            if maximum_date != date:
                warnings.warn(
                    f'{date.date()} is not the maximum day of its event; '
                    f'the maximum is {maximum_date.date()}')

        date_strings = [date.strftime('%Y-%m-%d') for date in event_dates]
        self.config['event_dates'] = date_strings
        self._save_config()
        event_frame = pd.DataFrame({
            'Date': date_strings,
            'ROVOL_acft': values.to_numpy(),
        })
        event_frame.to_csv(
            self.output_dir / f'peak_events_RCH{self.outlet_reach}.csv',
            index=False)
        row = {
            'scenario': 'baseline',
            'reach_id': self.outlet_reach,
            'reach_area': np.nan,
            'run_ok': True,
            'n_errors': 0,
            **dict(zip(date_strings, values.to_numpy())),
            'total_acft': total,
            'baseline_total_acft': total,
            'delta_acft': 0.0,
            'avg_area': self._average_area(),
            'allocation': np.nan,
            'allocation_baseline_ratio': np.nan,
        }
        pd.DataFrame([row]).to_csv(self.results_path, index=False)
        return event_frame

    def scenario_reaches(self):
        """Return scenario reaches in their OPN SEQUENCE order."""
        return [reach for reach in self._analysis_reaches()
                if reach != self.outlet_reach]

    def create_scenarios(self, reach_ids=None):
        """Create permanent UCIs for selected reach-removal scenarios."""
        eligible = self.scenario_reaches()
        if reach_ids is None:
            selected = eligible
        else:
            requested = {int(reach) for reach in reach_ids}
            invalid = requested.difference(eligible)
            if invalid:
                values = ', '.join(str(reach) for reach in sorted(invalid))
                raise ValueError(f'Reaches are not eligible PFA scenarios: {values}')
            selected = [reach for reach in eligible if reach in requested]
        paths = []
        for reach_id in selected:
            scenario = make_scenario_uci(
                self.baseline_uci_path, reach_id, self.outlet_reach)
            path = self.ucis_dir / f'{scenario_name(reach_id, self.outlet_reach)}.uci'
            scenario.write(path)
            paths.append(path)
        created = set(self.config.get('scenario_order', [])) | set(selected)
        self.config['scenario_order'] = [
            int(reach) for reach in eligible if reach in created]
        self._save_config()
        return paths

    def _completed_scenarios(self):
        if not self.results_path.exists():
            return set()
        frame = pd.read_csv(self.results_path, comment='#')
        if 'run_ok' not in frame or 'scenario' not in frame:
            return set()
        successful = frame['run_ok'].astype(str).str.lower() == 'true'
        return set(frame.loc[successful, 'scenario'].astype(str))

    def run_scenarios(self, batch_size=4, cleanup=True, reach_ids=None,
                      skip_completed=True):
        """Run selected scenario UCIs with bounded staging and extraction."""
        if not self.config.get('event_dates'):
            raise ValueError('Set peak events before running scenarios')
        eligible = self.scenario_reaches()
        if reach_ids is None:
            selected = eligible
        else:
            requested = {int(reach) for reach in reach_ids}
            invalid = requested.difference(eligible)
            if invalid:
                values = ', '.join(str(reach) for reach in sorted(invalid))
                raise ValueError(f'Reaches are not eligible PFA scenarios: {values}')
            selected = [reach for reach in eligible if reach in requested]
        uci_files = [
            self.ucis_dir / f'{scenario_name(reach, self.outlet_reach)}.uci'
            for reach in selected]
        missing = [path for path in uci_files if not path.exists()]
        if missing:
            raise FileNotFoundError(
                f'Scenario UCI does not exist: {missing[0]}. Call create_scenarios() first.')
        completed = self._completed_scenarios() if skip_completed else set()
        stage_files = [self.pfa_dir / name for name in self.config['wdm_files']]
        return run_batch_staged(
            uci_files, self.scenarios_dir, stage_files,
            batch_size=batch_size, on_complete=self.extract, cleanup=cleanup,
            skip_if=lambda path: path.stem in completed,
            log_csv=self.output_dir / 'run_log.csv')

    def _reach_from_scenario(self, path):
        stem = Path(path).stem
        suffix = f'_to_RCH{self.outlet_reach}'
        if not stem.startswith('RCH') or not stem.endswith(suffix):
            raise ValueError(f'Unexpected PFA scenario name: {stem}')
        return int(stem[3:-len(suffix)])

    def _write_result_row(self, row):
        if self.results_path.exists():
            results = pd.read_csv(self.results_path, comment='#')
            results = results.loc[results['scenario'] != row['scenario']]
            results = pd.concat([results, pd.DataFrame([row])], ignore_index=True)
        else:
            results = pd.DataFrame([row])
        temporary = self.results_path.with_suffix('.csv.tmp')
        results.to_csv(temporary, index=False)
        temporary.replace(self.results_path)

    def extract(self, uci_path, status):
        """Extract one staged run and persist its raw event results."""
        reach_id = self._reach_from_scenario(uci_path)
        name = scenario_name(reach_id, self.outlet_reach)
        event_dates = self.config.get('event_dates', [])
        if not self.results_path.exists():
            raise FileNotFoundError('Baseline results are unavailable; call set_peak_events()')
        existing = pd.read_csv(self.results_path, comment='#')
        baseline = existing.loc[existing['scenario'] == 'baseline']
        if baseline.empty:
            raise ValueError('Results CSV does not contain the baseline row')
        baseline_total = float(baseline.iloc[0]['total_acft'])
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        reach_area = float(model.network.subwatershed_area(reach_id))
        avg_area = self._average_area()
        row = {
            'scenario': name,
            'reach_id': reach_id,
            'reach_area': reach_area,
            'run_ok': bool(status['ok']),
            'n_errors': int(status['n_errors']),
            **{date: np.nan for date in event_dates},
            'total_acft': np.nan,
            'baseline_total_acft': baseline_total,
            'delta_acft': np.nan,
            'avg_area': avg_area,
            'allocation': np.nan,
            'allocation_baseline_ratio': np.nan,
        }
        if status['ok']:
            scenario = UCI(uci_path, infer_metzones=False)
            series = daily_rovol(scenario.hbn_paths, self.outlet_reach)
            values, total = event_totals(series, event_dates)
            delta = baseline_total - total
            alloc = allocation(baseline_total, total, avg_area, reach_area)
            row.update({
                **dict(zip(event_dates, values.to_numpy())),
                'total_acft': total,
                'delta_acft': delta,
                'allocation': alloc,
                'allocation_baseline_ratio': (
                    alloc / baseline_total if baseline_total else np.nan),
            })
        self._write_result_row(row)
        return row

    def results(self):
        """Return recomputed and ranked PFA results."""
        if not self.results_path.exists():
            raise FileNotFoundError('PFA results are not available')
        return analyze(self.results_path)

    def cleanup_baseline(self):
        """Remove baseline run products while preserving its UCI."""
        removable = {'.hbn', '.wdm', '.ech', '.log'}
        removed = []
        for path in self.baseline_dir.iterdir():
            if path.suffix.lower() in removable or path.name.upper() == 'ERROR.FIL':
                path.unlink()
                removed.append(path)
        return removed

    def summary(self):
        """Print and return the current PFA setup and progress summary."""
        model = UCI(self.baseline_uci_path, infer_metzones=False)
        analysis_reaches = self._analysis_reaches()
        summary = {
            'pfa_dir': str(self.pfa_dir),
            'outlet_reach': self.outlet_reach,
            'upstream_reaches': len(model.network._upstream(self.outlet_reach)),
            'routing_reaches_excluded': len(self.config.get('routing_reaches', [])),
            'scenario_reaches': len(analysis_reaches) - 1,
            'drainage_area_acres': model.network.drainage_area([self.outlet_reach]),
            'average_subwatershed_area_acres': self._average_area(),
            'event_dates': self.config.get('event_dates', []),
            'wdm_files': self.config.get('wdm_files', []),
            'completed_scenarios': len(
                self._completed_scenarios() - {'baseline'}),
        }
        print('\n'.join(f'{key}: {value}' for key, value in summary.items()))
        return summary
