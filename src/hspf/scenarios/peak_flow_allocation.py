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

    def map_allocation(self, subwatersheds_shp=None, reaches_shp=None,
                        output_dir=None, cmap=None, label_reaches=True,
                        basemap=True, basemap_source='Esri.WorldImagery',
                        add_mn_background=True,
                        add_watershed_boundary=True,
                        figsize=(14, 11),
                        watershed_name=None,
                        metrics='both',
                        subwatershed_fill='#E6DCC9',
                        subwatershed_edge='#888888',
                        reach_color='#295789',
                        reach_linewidth=1.5,
                        total_label=True,
                        total_label_position='upper-left'):
        """
        Create deliverable-quality PFA maps.

        This method always produces a reference subwatershed/reach map and one
        or more metric maps. The reference map shows neutral subwatersheds,
        semi-transparent blue reach lines, and reach number labels. Metric maps
        color subwatersheds by allocation, allocation/baseline ratio, or both,
        and label each subwatershed with its value(s). Titles and the total
        peak-flow volume are drawn as overlays inside the map.

        Parameters
        ----------
        subwatersheds_shp : Path-like, optional
            Path to a subwatersheds shapefile. If None, searches for
            '*_Subwatersheds.shp' in the GIS folder next to the source UCI.
        reaches_shp : Path-like, optional
            Path to a reaches shapefile. If None, searches for '*_Reaches.shp'
            in the GIS folder next to the source UCI.
        output_dir : Path-like, optional
            Directory to save the map PNGs. Defaults to ``self.output_dir``.
        cmap : str or matplotlib.colors.Colormap, optional
            Matplotlib colormap for metric maps. If None, uses a custom
            light-blue-to-dark-blue ramp.
        label_reaches : bool, optional
            If True, label each subwatershed with its upstream reach number on
            the reference map and with its allocation/ratio value(s) on metric
            maps.
        basemap : bool, optional
            If True, add an XYZ tile basemap using ``contextily``. If
            ``contextily`` is not installed, a warning is issued and the basemap
            is skipped.
        basemap_source : str, optional
            ``contextily`` / XYZ source name. Examples:
            ``'Esri.WorldImagery'``, ``'Esri.WorldStreetMap'``,
            ``'OpenStreetMap.Mapnik'``, ``'CartoDB.Positron'``,
            ``'USGS.USTopo'``.
        add_mn_background : bool, optional
            If True, draw the Minnesota background polygon shipped with the
            package as a light-grey backdrop.
        add_watershed_boundary : bool, optional
            If True, dissolve the model subwatersheds and draw the watershed
            boundary as a dark grey outline.
        figsize : tuple, optional
            Figure size in inches.
        watershed_name : str, optional
            Human-readable watershed name for map titles. If None, the project
            folder name is used (e.g., ``'NFCrow'``).
        metrics : {'allocation', 'ratio', 'both'} or list, optional
            Metrics to map. ``'both'`` draws one map with both scales.
            ``['allocation', 'ratio']`` draws two separate metric maps.
        subwatershed_fill : str, optional
            Fill color for subwatersheds on the reference map.
        subwatershed_edge : str, optional
            Outline color for subwatersheds on the reference map.
        reach_color : str, optional
            Line color for reaches on the reference map.
        reach_linewidth : float, optional
            Line width for reaches on the reference map.
        total_label : bool, optional
            If True, add the total peak-flow volume overlay to metric maps.
        total_label_position : str or tuple, optional
            Position of the total label on metric maps. Use ``'upper-left'``,
            ``'upper-right'``, ``'lower-left'``, ``'lower-right'``, or an
            ``(x, y)`` tuple in axes coordinates.

        Returns
        -------
        list of Path
            Paths to the saved map PNGs. The reference map is always first.

        TODO: Merge this maping function into mappers.py within phycal. Talk with Mulu to determine best location.
        """
        import matplotlib
        matplotlib.use('Agg', force=True)

        import geopandas as gpd
        import matplotlib.patheffects as path_effects
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap, Normalize
        from matplotlib.cm import ScalarMappable
        from mpl_toolkits.axes_grid1 import make_axes_locatable

        if cmap is None:
            cmap = LinearSegmentedColormap.from_list(
                'pfa_blue',
                ['#A8C8EC', '#6BAED6', '#2171B5', '#003865'])

        # Optional contextily basemap with graceful fallback.
        if basemap:
            try:
                import contextily as ctx
            except ImportError:
                warnings.warn(
                    'contextily is not installed; basemap will be disabled. '
                    'Install it with: pip install contextily')
                ctx = None
                basemap = False
        else:
            ctx = None

        results = self.results()
        scenario_results = results.loc[
            results['scenario'].astype(str).str.lower() != 'baseline'].copy()

        if watershed_name is None:
            watershed_name = Path(self.config['source_uci']).parent.parent.name

        baseline_row = results.loc[
            results['scenario'].astype(str).str.lower() == 'baseline']
        if baseline_row.empty:
            raise ValueError('Results CSV does not contain a baseline row')
        baseline_total = int(round(float(
            baseline_row.iloc[0]['baseline_total_acft'])))
        total_text = (
            f'Total peak-flow volume: {baseline_total:,} ac-ft')

        # Parse metrics argument.
        if metrics == 'both':
            metric_groups = [('allocation', 'ratio')]
        elif metrics == 'allocation':
            metric_groups = [('allocation',)]
        elif metrics == 'ratio':
            metric_groups = [('ratio',)]
        elif isinstance(metrics, (list, tuple)):
            metric_groups = [(m,) for m in metrics]
        else:
            raise ValueError(
                "metrics must be 'allocation', 'ratio', 'both', or a list of "
                "those strings")
        for group in metric_groups:
            for metric in group:
                if metric not in ('allocation', 'ratio'):
                    raise ValueError(
                        f"Unknown metric '{metric}'. Use 'allocation' or "
                        "'ratio'.")

        if subwatersheds_shp is None:
            source_uci = Path(self.config['source_uci'])
            gis_dir = source_uci.parent.parent / 'gis'
            candidates = sorted(gis_dir.glob('*_Subwatersheds.shp'))
            if not candidates:
                raise FileNotFoundError(
                    f'Could not find a *_Subwatersheds.shp file in {gis_dir}. '
                    'Pass subwatersheds_shp explicitly.')
            subwatersheds_shp = candidates[0]
        else:
            subwatersheds_shp = Path(subwatersheds_shp)
        if not subwatersheds_shp.exists():
            raise FileNotFoundError(subwatersheds_shp)

        subwatersheds = gpd.read_file(subwatersheds_shp)
        if 'SubID' not in subwatersheds.columns:
            raise ValueError(
                f"Subwatersheds shapefile {subwatersheds_shp.name} must "
                "contain a 'SubID' column")

        # Optional reaches shapefile.
        if reaches_shp is None:
            source_uci = Path(self.config['source_uci'])
            gis_dir = source_uci.parent.parent / 'gis'
            reach_candidates = sorted(gis_dir.glob('*_Reaches.shp'))
            if reach_candidates:
                reaches_shp = reach_candidates[0]
            else:
                reaches_shp = None
        if reaches_shp is not None:
            reaches_shp = Path(reaches_shp)
            if not reaches_shp.exists():
                reaches_shp = None
        reaches = gpd.read_file(reaches_shp) if reaches_shp else None

        # MN background shapefile shipped with the package.
        mn_background_path = (
            Path(__file__).resolve().parent / 'data' / 'MN_Background.shp')
        if add_mn_background and mn_background_path.exists():
            mn_background = gpd.read_file(mn_background_path)
        elif add_mn_background:
            warnings.warn(
                f'MN_Background shapefile not found at {mn_background_path}; '
                'skipping background layer.')
            mn_background = None
        else:
            mn_background = None

        # Use Web Mercator when a basemap is requested so contextily can place
        # tiles without reprojecting; otherwise use UTM 15N for Minnesota.
        if basemap and ctx is not None:
            map_crs = 'EPSG:3857'
        else:
            map_crs = 'EPSG:26915'
        subwatersheds = subwatersheds.to_crs(map_crs)
        if mn_background is not None:
            mn_background = mn_background.to_crs(map_crs)
        if reaches is not None:
            reaches = reaches.to_crs(map_crs)

        merged = subwatersheds.merge(
            scenario_results, left_on='SubID', right_on='reach_id', how='left')
        merged.geometry = merged.geometry.make_valid()
        merged['_allocation_baseline_ratio_pct'] = (
            merged['allocation_baseline_ratio'] * 100)

        if add_watershed_boundary:
            watershed_boundary = subwatersheds.dissolve()
            watershed_boundary.geometry = watershed_boundary.geometry.make_valid()
        else:
            watershed_boundary = None

        output_dir = Path(output_dir or self.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = f'peak_flow_allocation_RCH{self.outlet_reach}'
        paths = []

        def setup_base_layers(ax):
            """Add basemap, MN background, and watershed boundary."""
            # Plot an invisible boundary first to establish the watershed
            # extent, then extend the top margin so titles can sit on the
            # basemap without covering the watershed.
            merged.boundary.plot(ax=ax, color='none', linewidth=0)
            x_min, x_max = ax.get_xlim()
            y_min, y_max = ax.get_ylim()
            y_range = y_max - y_min
            new_y_max = y_max + 0.12 * y_range
            ax.set_ylim(y_min, new_y_max)

            if basemap and ctx is not None:
                ctx.add_basemap(
                    ax, source=basemap_source, attribution=False)

            if mn_background is not None:
                alpha = 0.65 if basemap else 1.0
                mn_background.plot(
                    ax=ax, color='#F5F5F5', edgecolor='grey',
                    linewidth=0.5, alpha=alpha, zorder=2)

            if watershed_boundary is not None:
                watershed_boundary.plot(
                    ax=ax, color='none', edgecolor='#4A4A4A',
                    linewidth=2, zorder=4)

            return (x_min, x_max, y_min, new_y_max)

        def add_reach_labels(ax):
            """Label each subwatershed with its upstream reach number."""
            if not label_reaches:
                return
            for _, row in merged.iterrows():
                reach_id = row.get('reach_id')
                if pd.notna(reach_id):
                    point = row.geometry.representative_point()
                    ax.text(
                        point.x, point.y, str(int(reach_id)),
                        fontsize=5, ha='center', va='center',
                        color='white', zorder=6,
                        path_effects=[
                            path_effects.withStroke(
                                linewidth=0.8, foreground='black')])

        def add_value_labels(ax, metric):
            """Label each subwatershed with its allocation and/or ratio."""
            if not label_reaches:
                return
            for _, row in merged.iterrows():
                reach_id = row.get('reach_id')
                if not pd.notna(reach_id):
                    continue
                alloc = row.get('allocation')
                ratio = row.get('_allocation_baseline_ratio_pct')
                if metric == 'allocation':
                    if pd.isna(alloc):
                        continue
                    text = f'{alloc:.1f}'
                elif metric == 'ratio':
                    if pd.isna(ratio):
                        continue
                    text = f'{ratio:.2f}%'
                else:
                    if pd.isna(alloc) and pd.isna(ratio):
                        continue
                    text = f'{alloc:.1f}\n({ratio:.2f}%)'
                point = row.geometry.representative_point()
                ax.text(
                    point.x, point.y, text,
                    fontsize=4.5, ha='center', va='center',
                    color='white', zorder=6,
                    path_effects=[
                        path_effects.withStroke(
                            linewidth=0.8, foreground='black')])

        def add_total_label(ax):
            """Add the total peak-flow volume overlay."""
            if not total_label:
                return
            if isinstance(total_label_position, str):
                position_map = {
                    'upper-left': (0.02, 0.98, 'top'),
                    'upper-right': (0.98, 0.98, 'top'),
                    'lower-left': (0.02, 0.02, 'bottom'),
                    'lower-right': (0.98, 0.02, 'bottom'),
                }
                if total_label_position not in position_map:
                    raise ValueError(
                        f"Unknown total_label_position '{total_label_position}'. "
                        "Use 'upper-left', 'upper-right', 'lower-left', "
                        "'lower-right', or an (x, y) tuple.")
                x, y, va = position_map[total_label_position]
            else:
                x, y = total_label_position
                va = 'top'
            ax.text(
                x, y, total_text,
                transform=ax.transAxes, fontsize=10,
                verticalalignment=va, zorder=10,
                bbox=dict(boxstyle='round', facecolor='white',
                          edgecolor='black', alpha=0.85))

        def add_title(ax, title):
            """Draw the map title inside the top margin of the map."""
            ax.text(
                0.5, 0.96, title,
                transform=ax.transAxes, fontsize=14,
                ha='center', va='top', zorder=10,
                bbox=dict(boxstyle='round', facecolor='white',
                          edgecolor='black', alpha=0.85))

        # Reference subwatershed / reach map.
        fig, ax = plt.subplots(figsize=figsize)
        limits = setup_base_layers(ax)
        subwatersheds.plot(
            ax=ax, facecolor=subwatershed_fill, edgecolor=subwatershed_edge,
            linewidth=0.5, zorder=3)
        if reaches is not None:
            reaches.plot(
                ax=ax, color=reach_color, linewidth=reach_linewidth,
                alpha=0.7, zorder=4)
        add_reach_labels(ax)
        ax.set_xlim(limits[0], limits[1])
        ax.set_ylim(limits[2], limits[3])
        add_title(ax, f'{watershed_name} HSPF Subwatersheds')
        ax.set_axis_off()
        ref_path = output_dir / f'{base_name}_subwatersheds.png'
        fig.savefig(ref_path, dpi=300, bbox_inches='tight')
        plt.close(fig)
        paths.append(ref_path)

        # Metric maps.
        metric_titles = {
            ('allocation',): f'{watershed_name} Peak Flow Allocation (ac-ft)',
            ('ratio',): f'{watershed_name} Allocation / Baseline (%)',
            ('allocation', 'ratio'): f'{watershed_name} Peak Flow Allocation',
        }
        metric_filenames = {
            ('allocation',): f'{base_name}_allocation.png',
            ('ratio',): f'{base_name}_ratio.png',
            ('allocation', 'ratio'): f'{base_name}.png',
        }

        for group in metric_groups:
            fig, ax = plt.subplots(figsize=figsize)
            limits = setup_base_layers(ax)

            if group == ('allocation',):
                plot_col = 'allocation'
            elif group == ('ratio',):
                plot_col = '_allocation_baseline_ratio_pct'
            else:
                plot_col = 'allocation'

            merged.plot(
                column=plot_col, ax=ax, cmap=cmap, legend=False,
                edgecolor='grey', linewidth=0.3, zorder=5,
                missing_kwds={'color': 'lightgrey', 'label': 'No data'})

            label_metric = 'both' if len(group) > 1 else group[0]
            add_value_labels(ax, label_metric)

            # Side-by-side color scales (ratio closest to map, allocation to
            # the right) when both metrics are requested.
            divider = make_axes_locatable(ax)
            pad_values = [0.05, 0.55]
            for index, metric in enumerate(group):
                cax = divider.append_axes(
                    'right', size='4%', pad=pad_values[index])
                if metric == 'allocation':
                    values = merged['allocation'].dropna()
                    label = 'Allocation (ac-ft)'
                    fmt = '%.1f'
                else:
                    values = merged['_allocation_baseline_ratio_pct'].dropna()
                    label = 'Allocation / Baseline (%)'
                    fmt = '%.3f'
                norm = Normalize(
                    vmin=float(values.min()), vmax=float(values.max()))
                sm = ScalarMappable(norm=norm, cmap=cmap)
                cbar = fig.colorbar(sm, cax=cax, format=fmt)
                cbar.set_label(label, rotation=270, labelpad=18)

            add_total_label(ax)
            ax.set_xlim(limits[0], limits[1])
            ax.set_ylim(limits[2], limits[3])
            add_title(ax, metric_titles[group])
            ax.set_axis_off()

            metric_path = output_dir / metric_filenames[group]
            fig.savefig(metric_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            paths.append(metric_path)

        return paths

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
