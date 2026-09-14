import csv
from pathlib import Path
import shutil

from hspf import hspfModel


DATA = Path(__file__).parent / 'data' / 'Clearwater.uci'


def copy_uci(tmp_path, name='scenario.uci'):
    path = tmp_path / name
    shutil.copy2(DATA, path)
    return path


def test_run_uci_defaults_cwd_to_uci_folder(tmp_path, monkeypatch):
    uci_path = copy_uci(tmp_path)
    calls = []

    def fake_run(args, cwd):
        calls.append((args, cwd))
        return 'completed'

    monkeypatch.setattr(hspfModel.subprocess, 'run', fake_run)

    result = hspfModel.run_uci(uci_path)

    assert result == 'completed'
    assert calls[0][0][1] == uci_path.resolve().as_posix()
    assert calls[0][1] == tmp_path


def test_check_run_status_uses_messu_and_ignores_warning_text(tmp_path):
    uci_path = copy_uci(tmp_path)
    echo = tmp_path / 'CLWM.ech'
    echo.write_text(
        'ERROR/WARNING ID: 218 13\n'
        'The continuity error reported below is greater than 1 part in 1000.\n'
        'RELERR is the relative error (ERROR/REFVAL).\n'
        'ERROR is (STOR-STORS) - MATDIF.\n'
        'End of Job\n'
    )

    status = hspfModel.check_run_status(uci_path)

    assert status['ok']
    assert status['end_of_job']
    assert status['n_errors'] == 0
    assert status['ech_path'] == echo
    assert status['log_path'] == tmp_path / 'scenario.log'


def test_check_run_status_reports_errors_and_incomplete_runs(tmp_path):
    uci_path = copy_uci(tmp_path)
    echo = tmp_path / 'CLWM.ech'
    echo.write_text('ERROR opening input WDM\n')

    status = hspfModel.check_run_status(uci_path)

    assert not status['ok']
    assert not status['end_of_job']
    assert status['n_errors'] == 1
    assert status['errors'] == ['ERROR opening input WDM']


def test_run_batch_staged_extracts_then_cleans_and_logs(tmp_path, monkeypatch):
    uci_dir = tmp_path / 'ucis'
    uci_dir.mkdir()
    first = copy_uci(uci_dir, 'first.uci')
    second = copy_uci(uci_dir, 'second.uci')
    stage_file = tmp_path / 'input.wdm'
    stage_file.write_text('staged')
    completed = []

    def fake_run(uci_path, cwd=None):
        assert (Path(cwd) / 'input.wdm').read_text() == 'staged'
        (Path(cwd) / 'CLWM.ech').write_text('End of Job\n')

    def extract(uci_path, status):
        assert Path(uci_path).exists()
        assert status['ok']
        completed.append(Path(uci_path).stem)
        return Path(uci_path).stem.upper()

    monkeypatch.setattr(hspfModel, 'run_uci', fake_run)
    run_root = tmp_path / 'runs'
    log_csv = tmp_path / 'run_log.csv'

    results = hspfModel.run_batch_staged(
        [first, second], run_root, [stage_file], batch_size=2,
        on_complete=extract, cleanup=True, log_csv=log_csv)

    assert set(completed) == {'first', 'second'}
    assert {result for _, _, result in results} == {'FIRST', 'SECOND'}
    assert not (run_root / 'first').exists()
    assert not (run_root / 'second').exists()
    with log_csv.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert {row['scenario'] for row in rows} == {'first', 'second'}
    assert all(row['ok'] == 'True' for row in rows)
    assert all(row['run_dir_kept'] == 'False' for row in rows)


def test_run_batch_staged_skips_completed_and_keeps_failures(tmp_path, monkeypatch):
    uci_dir = tmp_path / 'ucis'
    uci_dir.mkdir()
    skipped = copy_uci(uci_dir, 'skipped.uci')
    failed = copy_uci(uci_dir, 'failed.uci')
    callbacks = []

    def fake_run(uci_path, cwd=None):
        (Path(cwd) / 'CLWM.ech').write_text('ERROR failed run\n')

    monkeypatch.setattr(hspfModel, 'run_uci', fake_run)
    run_root = tmp_path / 'runs'

    results = hspfModel.run_batch_staged(
        [skipped, failed], run_root, [], batch_size=1,
        on_complete=lambda path, status: callbacks.append(status['ok']),
        skip_if=lambda path: path.stem == 'skipped')

    assert len(results) == 1
    assert callbacks == [False]
    assert (run_root / 'failed').exists()
    assert not (run_root / 'skipped').exists()


def test_run_batch_staged_rejects_nonzero_process_returncode(tmp_path, monkeypatch):
    uci_path = copy_uci(tmp_path, 'nonzero.uci')

    class Completed:
        returncode = 1

    def fake_run(path, cwd=None):
        (Path(cwd) / 'CLWM.ech').write_text('End of Job\n')
        return Completed()

    monkeypatch.setattr(hspfModel, 'run_uci', fake_run)

    results = hspfModel.run_batch_staged(
        [uci_path], tmp_path / 'runs', [], batch_size=1)

    assert not results[0][1]['ok']
    assert results[0][1]['returncode'] == 1
    assert (tmp_path / 'runs' / 'nonzero').exists()
