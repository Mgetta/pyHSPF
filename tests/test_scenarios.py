from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from hspf.uci import UCI
from hspf.scenarios import peak_flow_allocation as pfa


DATA = Path(__file__).parent / 'data' / 'Clearwater.uci'


def test_scenario_name():
    assert pfa.scenario_name(21, 990) == 'RCH21_to_RCH990'


def test_make_baseline_uci_sets_daily_outlet_and_trims_other_output():
    model = UCI(DATA, infer_metzones=False)
    outlet = model.network.outlets()[0]

    result = pfa.make_baseline_uci(model, outlet)

    binary_info = result.table('RCHRES', 'BINARY-INFO')
    assert result is model
    assert binary_info.loc[outlet, 'HYDRPR'] == 3
    assert (binary_info.drop(index=outlet)['HYDRPR'] == 6).all()


def test_make_baseline_uci_rejects_unknown_outlet():
    model = UCI(DATA, infer_metzones=False)

    with pytest.raises(ValueError, match='not in OPN SEQUENCE'):
        pfa.make_baseline_uci(model, 999999)


def test_make_scenario_uci_zeroes_local_land_and_reach_precipitation(tmp_path):
    baseline = tmp_path / 'baseline.uci'
    shutil.copy2(DATA, baseline)
    original = UCI(baseline, infer_metzones=False)
    reach_id = original.valid_opnids['RCHRES'][0]
    before = original.table('SCHEMATIC', drop_comments=False)
    sources_before = original.table('EXT SOURCES', drop_comments=False)

    scenario = pfa.make_scenario_uci(baseline, reach_id, 650)

    after = scenario.table('SCHEMATIC', drop_comments=False)
    target = ((after['TVOL'] == 'RCHRES') &
              (after['TVOLNO'] == reach_id) &
              after['SVOL'].isin(['PERLND', 'IMPLND']))
    assert (after.loc[target, 'AFACTR'].astype(float) == 0).all()
    pd.testing.assert_frame_equal(before.loc[~target], after.loc[~target])

    sources_after = scenario.table('EXT SOURCES', drop_comments=False)
    precipitation = ((sources_after['TVOL'] == 'RCHRES') &
                     (sources_after['TOPFST'] == reach_id) &
                     (sources_after['TMEMN'] == 'PREC'))
    assert precipitation.any()
    assert (sources_after.loc[precipitation, 'MFACTOR'].astype(float) == 0).all()
    pd.testing.assert_frame_equal(
        sources_before.loc[~precipitation], sources_after.loc[~precipitation])

    bino = scenario.table('FILES').query("FTYPE == 'BINO'")['FILENAME']
    assert bino.str.startswith('RCH10_to_RCH650-').all()
    output = tmp_path / 'scenario.uci'
    scenario.write(output)
    reread = UCI(output, infer_metzones=False).table('EXT SOURCES')
    precipitation = ((reread['TVOL'] == 'RCHRES') &
                     (reread['TOPFST'] == reach_id) &
                     (reread['TMEMN'] == 'PREC'))
    assert (reread.loc[precipitation, 'MFACTOR'].astype(float) == 0).all()


def test_daily_rovol_uses_daily_acre_feet(monkeypatch):
    calls = []
    expected = pd.Series(
        [10.0, 12.0], index=pd.date_range('2020-01-01', periods=2))

    class FakeInterface:
        def __init__(self, paths):
            self.paths = paths

    def fake_flow(interface, time_step, reach_ids, unit=None):
        calls.append((interface.paths, time_step, reach_ids, unit))
        return expected.copy()

    monkeypatch.setattr(pfa.hbn, 'hbnInterface', FakeInterface)
    monkeypatch.setattr(pfa.hbn, 'get_simulated_flow', fake_flow)

    result = pfa.daily_rovol(['one.hbn'], 990)

    pd.testing.assert_series_equal(result, expected.rename('ROVOL_acft'))
    assert calls == [(['one.hbn'], 'daily', [990], 'acrft')]


def test_write_sorted_flow_csv(tmp_path):
    series = pd.Series(
        [2.0, 5.0, 3.0],
        index=pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-03']))
    output = tmp_path / 'flows.csv'

    result = pfa.write_sorted_flow_csv(series, output)

    assert result == output
    assert output.read_text().startswith('# Daily outlet ROVOL')
    frame = pd.read_csv(output, comment='#')
    assert frame['Date'].tolist() == ['2020-01-02', '2020-01-03', '2020-01-01']
    assert frame['ROVOL_acft'].tolist() == [5.0, 3.0, 2.0]


def test_event_totals_preserves_requested_order_and_validates_dates():
    series = pd.Series(
        [1.0, 2.0, 3.0], index=pd.date_range('2020-01-01', periods=3))

    values, total = pfa.event_totals(series, ['2020-01-03', '2020-01-01'])

    assert values.tolist() == [3.0, 1.0]
    assert total == 4.0
    with pytest.raises(ValueError, match='2020-01-04'):
        pfa.event_totals(series, ['2020-01-04'])


def test_allocation_formula_and_area_validation():
    assert pfa.allocation(100, 80, 50, 10) == 100
    with pytest.raises(ValueError, match='positive'):
        pfa.allocation(100, 80, 50, 0)


def test_analyze_recomputes_metrics_and_ranks_scenarios(tmp_path):
    path = tmp_path / 'results.csv'
    pd.DataFrame([
        {'scenario': 'baseline', 'reach_area': np.nan, 'total_acft': 100,
         'avg_area': 50},
        {'scenario': 'RCH1_to_RCH9', 'reach_area': 10, 'total_acft': 80,
         'avg_area': 50},
        {'scenario': 'RCH2_to_RCH9', 'reach_area': 20, 'total_acft': 90,
         'avg_area': 50},
    ]).to_csv(path, index=False)

    result = pfa.analyze(path)

    assert result['baseline_total_acft'].tolist() == [100, 100, 100]
    assert result['delta_acft'].tolist() == [0, 20, 10]
    assert np.isnan(result.loc[0, 'allocation'])
    assert result.loc[1, 'allocation'] == 100
    assert result.loc[2, 'allocation'] == 25
    assert result.loc[1, 'pct_of_baseline'] == 0.2
    assert result.loc[1, 'rank'] == 1
    assert result.loc[2, 'rank'] == 2
    assert np.isnan(result.loc[0, 'rank'])


def make_project(tmp_path):
    model_dir = tmp_path / 'project' / 'model'
    model_dir.mkdir(parents=True)
    uci_path = model_dir / 'Clearwater.uci'
    shutil.copy2(DATA, uci_path)
    (model_dir / 'CLWRmet.wdm').write_text('met')
    (model_dir / 'CLWRps.wdm').write_text('sources')
    (tmp_path / 'project' / 'RLRlinkage.wdm').write_text('linkage')
    return uci_path


def test_peak_flow_allocation_setup_stages_inputs_and_baseline(tmp_path):
    uci_path = make_project(tmp_path)

    workflow = pfa.PeakFlowAllocation.setup(uci_path, outlet_reach=650)

    assert workflow.config_path.exists()
    assert workflow.baseline_uci_path.exists()
    assert (workflow.ucis_dir / 'baseline_RCH650.uci').exists()
    assert set(workflow.config['wdm_files']) == {
        'CLWRmet.wdm', 'CLWRps.wdm', 'RLRlinkage.wdm'}
    baseline = UCI(workflow.baseline_uci_path, infer_metzones=False)
    assert all(path.parent == workflow.baseline_dir for path in baseline.wdm_paths)
    assert all(path.exists() for path in baseline.wdm_paths)
    assert all(path.parent == workflow.baseline_dir for path in baseline.hbn_paths)
    assert baseline.table('RCHRES', 'BINARY-INFO').loc[650, 'HYDRPR'] == 3

    resumed = pfa.PeakFlowAllocation(workflow.pfa_dir, 650)
    assert resumed.config == workflow.config
    with pytest.raises(FileExistsError):
        pfa.PeakFlowAllocation.setup(uci_path, outlet_reach=650)


def test_run_baseline_saves_flow_outputs(tmp_path, monkeypatch):
    workflow = pfa.PeakFlowAllocation.setup(make_project(tmp_path), 650)
    series = pd.Series(
        [1.0, 5.0, 3.0], index=pd.date_range('2020-01-01', periods=3))
    calls = []

    monkeypatch.setattr(
        pfa, 'run_uci',
        lambda path, cwd=None: calls.append((Path(path), Path(cwd))))
    monkeypatch.setattr(
        pfa, 'check_run_status',
        lambda path: {'ok': True, 'end_of_job': True, 'n_errors': 0,
                      'errors': [], 'ech_path': None, 'log_path': None})
    monkeypatch.setattr(pfa, 'daily_rovol', lambda paths, reach: series.copy())
    monkeypatch.setattr(pfa.os, 'startfile', lambda path: calls.append(Path(path)),
                        raising=False)

    status = workflow.run_baseline()

    assert status['ok']
    assert workflow.baseline_timeseries_path.exists()
    assert status['flow_csv'].exists()
    assert calls[0] == (workflow.baseline_uci_path, workflow.baseline_dir)
    saved = pd.read_csv(workflow.baseline_timeseries_path)
    assert saved['ROVOL_acft'].tolist() == [1.0, 5.0, 3.0]


def test_run_baseline_retains_failed_run(tmp_path, monkeypatch):
    workflow = pfa.PeakFlowAllocation.setup(make_project(tmp_path), 650)
    monkeypatch.setattr(pfa, 'run_uci', lambda path, cwd=None: None)
    monkeypatch.setattr(
        pfa, 'check_run_status',
        lambda path: {'ok': False, 'end_of_job': False, 'n_errors': 1,
                      'errors': ['ERROR test'], 'ech_path': None,
                      'log_path': None})

    status = workflow.run_baseline()

    assert not status['ok']
    assert not workflow.baseline_timeseries_path.exists()


def test_suggest_and_set_peak_events_persist_outputs(tmp_path, monkeypatch):
    workflow = pfa.PeakFlowAllocation.setup(make_project(tmp_path), 650)
    index = pd.date_range('2020-01-01', periods=40)
    values = np.ones(40)
    values[[5, 20, 35]] = [10, 20, 15]
    pd.DataFrame({'Date': index, 'ROVOL_acft': values}).to_csv(
        workflow.baseline_timeseries_path, index=False)

    suggestions = workflow.suggest_peak_events(n=2, min_separation_days=5)
    events = workflow.set_peak_events(['2020-01-21', '2020-02-05'])

    assert len(suggestions) == 3
    assert suggestions.iloc[0]['datetime'] == pd.Timestamp('2020-01-21')
    assert events['Date'].tolist() == ['2020-01-21', '2020-02-05']
    assert workflow.config['event_dates'] == ['2020-01-21', '2020-02-05']
    assert workflow.results_path.exists()
    results = pd.read_csv(workflow.results_path)
    assert results.loc[0, 'scenario'] == 'baseline'
    assert results.loc[0, 'total_acft'] == 35

    resumed = pfa.PeakFlowAllocation(workflow.pfa_dir, 650)
    assert resumed.config['event_dates'] == workflow.config['event_dates']


def test_summary_and_cleanup_baseline(tmp_path):
    workflow = pfa.PeakFlowAllocation.setup(make_project(tmp_path), 650)
    for name in ['run.hbn', 'run.ech', 'run.log', 'ERROR.FIL']:
        (workflow.baseline_dir / name).write_text('output')

    summary = workflow.summary()
    removed = workflow.cleanup_baseline()

    assert summary['outlet_reach'] == 650
    assert summary['scenario_reaches'] == 140
    assert {path.name for path in removed}.issuperset(
        {'run.hbn', 'run.ech', 'run.log', 'ERROR.FIL'})
    assert workflow.baseline_uci_path.exists()


def prepared_workflow(tmp_path):
    workflow = pfa.PeakFlowAllocation.setup(make_project(tmp_path), 650)
    index = pd.date_range('2020-01-01', periods=30)
    values = np.ones(30)
    values[[4, 19]] = [10, 20]
    pd.DataFrame({
        'Date': index,
        'ROVOL_acft': values,
    }).to_csv(workflow.baseline_timeseries_path, index=False)
    workflow.set_peak_events(['2020-01-05', '2020-01-20'])
    return workflow


def test_scenario_reaches_and_create_scenarios(tmp_path):
    workflow = prepared_workflow(tmp_path)

    reaches = workflow.scenario_reaches()
    paths = workflow.create_scenarios(reach_ids=[reaches[0]])

    assert len(reaches) == 140
    assert 650 not in reaches
    assert len(paths) == 1
    assert paths[0].name == f'RCH{reaches[0]}_to_RCH650.uci'
    scenario = UCI(paths[0], infer_metzones=False)
    schematic = scenario.table('SCHEMATIC')
    target = ((schematic['TVOL'] == 'RCHRES') &
              (schematic['TVOLNO'] == reaches[0]) &
              schematic['SVOL'].isin(['PERLND', 'IMPLND']))
    assert (schematic.loc[target, 'AFACTR'].astype(float) == 0).all()
    assert workflow.config['scenario_order'] == [reaches[0]]


def test_run_scenarios_passes_staging_restart_and_extraction(tmp_path, monkeypatch):
    workflow = prepared_workflow(tmp_path)
    reach_id = workflow.scenario_reaches()[0]
    scenario_path = workflow.create_scenarios([reach_id])[0]
    captured = {}

    def fake_batch(uci_files, run_root, stage_files, **kwargs):
        captured.update({
            'uci_files': uci_files,
            'run_root': run_root,
            'stage_files': stage_files,
            **kwargs,
        })
        return ['ran']

    monkeypatch.setattr(pfa, 'run_batch_staged', fake_batch)

    result = workflow.run_scenarios(reach_ids=[reach_id], batch_size=2)

    assert result == ['ran']
    assert captured['uci_files'] == [scenario_path]
    assert captured['run_root'] == workflow.scenarios_dir
    assert captured['batch_size'] == 2
    assert captured['on_complete'] == workflow.extract
    assert not captured['skip_if'](scenario_path)
    assert all(path.exists() for path in captured['stage_files'])


def test_extract_writes_success_and_failed_rows_atomically(tmp_path, monkeypatch):
    workflow = prepared_workflow(tmp_path)
    first, second = workflow.scenario_reaches()[:2]
    first_path, second_path = workflow.create_scenarios([first, second])
    scenario_values = np.zeros(30)
    scenario_values[[4, 19]] = [9, 19]
    scenario_series = pd.Series(
        scenario_values, index=pd.date_range('2020-01-01', periods=30))
    monkeypatch.setattr(
        pfa, 'daily_rovol', lambda paths, reach: scenario_series.copy())

    success = workflow.extract(
        first_path, {'ok': True, 'n_errors': 0})
    failed = workflow.extract(
        second_path, {'ok': False, 'n_errors': 2})

    assert success['total_acft'] == 28
    assert success['delta_acft'] == 2
    assert success['allocation'] > 0
    assert not failed['run_ok']
    assert np.isnan(failed['total_acft'])
    assert not workflow.results_path.with_suffix('.csv.tmp').exists()
    saved = pd.read_csv(workflow.results_path)
    assert saved['scenario'].tolist() == [
        'baseline', pfa.scenario_name(first, 650),
        pfa.scenario_name(second, 650)]

    results = workflow.results()
    assert results.loc[results['scenario'] == pfa.scenario_name(first, 650),
                       'rank'].iloc[0] == 1


def test_successful_rerun_replaces_failure_and_enables_restart_skip(
        tmp_path, monkeypatch):
    workflow = prepared_workflow(tmp_path)
    reach_id = workflow.scenario_reaches()[0]
    scenario_path = workflow.create_scenarios([reach_id])[0]
    workflow.extract(scenario_path, {'ok': False, 'n_errors': 1})
    assert pfa.scenario_name(reach_id, 650) not in workflow._completed_scenarios()

    values = np.ones(30)
    values[[4, 19]] = [10, 20]
    series = pd.Series(values, index=pd.date_range('2020-01-01', periods=30))
    monkeypatch.setattr(pfa, 'daily_rovol', lambda paths, reach: series)
    workflow.extract(scenario_path, {'ok': True, 'n_errors': 0})

    assert pfa.scenario_name(reach_id, 650) in workflow._completed_scenarios()
    saved = pd.read_csv(workflow.results_path)
    assert (saved['scenario'] == pfa.scenario_name(reach_id, 650)).sum() == 1


def test_run_scenarios_requires_events_and_created_ucis(tmp_path):
    workflow = pfa.PeakFlowAllocation.setup(make_project(tmp_path), 650)
    reach_id = workflow.scenario_reaches()[0]

    with pytest.raises(ValueError, match='Set peak events'):
        workflow.run_scenarios(reach_ids=[reach_id])

    workflow.config['event_dates'] = ['2020-01-01']
    workflow._save_config()
    with pytest.raises(FileNotFoundError, match='create_scenarios'):
        workflow.run_scenarios(reach_ids=[reach_id])
