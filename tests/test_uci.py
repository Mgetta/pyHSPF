from pathlib import Path

import pandas as pd

from hspf.uci import (
    UCI,
    remove_operations,
    remove_routing_reaches,
    reroute_reaches,
    set_schematic_area,
    setup_binaryinfo,
)


DATA = Path(__file__).parent / 'data' / 'Clearwater.uci'


def load_uci():
    return UCI(DATA, infer_metzones=False)


def test_set_schematic_area_preserves_other_sources_and_round_trips(tmp_path):
    model = load_uci()
    reach_id = 10
    before = model.table('SCHEMATIC', drop_comments=False)
    target = ((before['TVOL'] == 'RCHRES') &
              (before['TVOLNO'] == reach_id) &
              before['SVOL'].isin(['PERLND', 'IMPLND']))
    untouched = ((before['TVOL'] == 'RCHRES') &
                 (before['TVOLNO'] == reach_id) & ~target)

    set_schematic_area(model, [reach_id])

    after = model.table('SCHEMATIC', drop_comments=False)
    assert (after.loc[target, 'AFACTR'].astype(float) == 0).all()
    pd.testing.assert_frame_equal(after.loc[untouched], before.loc[untouched])

    output = tmp_path / 'area_zero.uci'
    model.write(output)
    reread = UCI(output, infer_metzones=False).table('SCHEMATIC')
    reread_target = ((reread['TVOL'] == 'RCHRES') &
                     (reread['TVOLNO'] == reach_id) &
                     reread['SVOL'].isin(['PERLND', 'IMPLND']))
    assert (reread.loc[reread_target, 'AFACTR'].astype(float) == 0).all()


def test_remove_operations_preserves_comments_and_round_trips(tmp_path):
    model = load_uci()
    reach_id = model.valid_opnids['RCHRES'][0]
    comments = [line for line in model.table_lines('OPN SEQUENCE') if line.lstrip().startswith('***')]

    remove_operations(model, 'RCHRES', [reach_id])

    assert reach_id not in model.valid_opnids['RCHRES']
    assert comments == [line for line in model.table_lines('OPN SEQUENCE') if line.lstrip().startswith('***')]

    output = tmp_path / 'operation_removed.uci'
    model.write(output)
    reread = UCI(output, infer_metzones=False)
    assert reach_id not in reread.valid_opnids['RCHRES']


def test_reroute_reaches_redirects_incoming_rows():
    model = load_uci()
    schematic = model.table('SCHEMATIC', drop_comments=False)
    routes = schematic[(schematic['SVOL'] == 'RCHRES') &
                       (schematic['TVOL'] == 'RCHRES')]
    incoming_ids = set(routes['TVOLNO'].astype(int))
    reach_id = next(int(row.SVOLNO) for row in routes.itertuples()
                    if int(row.SVOLNO) in incoming_ids)
    destination = int(routes.loc[routes['SVOLNO'] == reach_id, 'TVOLNO'].iloc[0])
    upstream = routes.loc[routes['TVOLNO'] == reach_id, 'SVOLNO'].astype(int).tolist()

    reroute_reaches(model, [reach_id])

    after = model.table('SCHEMATIC')
    redirected = after[(after['SVOL'] == 'RCHRES') &
                       after['SVOLNO'].isin(upstream)]
    assert set(redirected['TVOLNO'].astype(int)) == {destination}
    assert not ((after['SVOL'] == 'RCHRES') &
                (after['SVOLNO'] == reach_id)).any()


def test_remove_routing_reach_preserves_upstream_area(tmp_path):
    model = load_uci()
    schematic = model.table('SCHEMATIC')
    routes = schematic[(schematic['SVOL'] == 'RCHRES') &
                       (schematic['TVOL'] == 'RCHRES')]
    incoming_ids = set(routes['TVOLNO'].astype(int))
    reach_id = next(int(row.SVOLNO) for row in routes.itertuples()
                    if int(row.SVOLNO) in incoming_ids)
    outlet = model.network.outlets()[0]

    set_schematic_area(model, [reach_id])
    model.rebuild_network()
    area_before = model.network.drainage_area([outlet])
    upstream_before = set(model.network._upstream(outlet))
    assert reach_id in model.network.routing_reaches

    removed = remove_routing_reaches(model, [reach_id])

    assert removed == [reach_id]
    assert reach_id not in model.valid_opnids['RCHRES']
    assert model.network.drainage_area([outlet]) == area_before
    assert set(model.network._upstream(outlet)) == upstream_before - {reach_id}

    output = tmp_path / 'routing_removed.uci'
    model.write(output)
    reread = UCI(output, infer_metzones=False)
    assert reach_id not in reread.table('RCHRES', 'HYDR-PARM2').index
    assert reach_id not in reread.table('RCHRES', 'BINARY-INFO').index
    external_sources = reread.table('EXT SOURCES')
    removed_targets = ((external_sources['TVOL'] == 'RCHRES') &
                       (external_sources['TOPFST'] == reach_id))
    assert not removed_targets.any()


def test_setup_binaryinfo_accepts_reach_output():
    model = load_uci()
    reach_id = model.valid_opnids['RCHRES'][0]

    setup_binaryinfo(model, default_output=6, reach_ids=[reach_id],
                     constituents=['Q'], reach_output=3)

    binary_info = model.table('RCHRES', 'BINARY-INFO')
    assert binary_info.loc[reach_id, 'HYDRPR'] == 3
    assert (binary_info.drop(index=reach_id)['HYDRPR'] == 6).all()
