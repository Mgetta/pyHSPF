from hspf.parser import graph
from pathlib import Path

from hspf.uci import UCI




uci = UCI(Path(__file__).parent.joinpath('data\Clearwater.uci'))


def test_lakes():
    assert uci.network._lakes() == [12,
                                    32,
                                    52,
                                    112,
                                    114,
                                    140,
                                    152,
                                    172,
                                    214,
                                    272,
                                    434,
                                    442,
                                    446,
                                    502,
                                    504,
                                    512,
                                    522,
                                    532,
                                    542,
                                    592,
                                    594,
                                    596,
                                    636]

def test_calibration_order():
    orders = graph.calibration_order(graph.make_watershed(uci.network.G,[90]))
    test_orders = [[52,53,10,12,32,71],
                    [55,13],
                    [30],
                    [50],
                    [70],
                    [90]]
    assert(len(orders) == len(test_orders))
    for order,test_order in zip(orders,test_orders):
        assert set(order) == set(test_order)
                                           
def test_get_opnids():
    opnids = uci.network.get_opnids('RCHRES',[90])
    expected_opnids = [10,12,13,30,32,50,52,53,55,70,71,90]
    assert set(opnids) == set(expected_opnids)

'''
Methods of the Network class:
_downstream',
 '_lakes',
 '_routing_reaches',
 '_upstream',
 'calibration_order',
 'catchment_ids',
 'downstream',
 'drainage',
 'drainage_area',
 'drainage_area_landcover',
 'get_node_type_ids',
 'get_opnids',
 'lake_area',
 'lakes',
 'operation_area',
 'outlets',
 'paths',
 'reach_contributions',
 'routing_reaches',
 'schematic',
 'station_order',
 'subwatershed',
 'subwatershed_area',
 'subwatersheds',
 'uci',
 'upstream'
'''




