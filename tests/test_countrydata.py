import pytest

from unfccc.etf.countrydata import CountryData


@pytest.fixture
def raw_countrydata():
    return {
        'country_specific_data': {
            'nodes': [
                {
                    'name': 'example parent node',
                    'uid': 'uid0',
                    'template_node_uid' : 'uid1',
                },
                {
                    'name': 'example child node',
                    'uid': 'uid2',
                    'parent_uid': 'uid0',
                    'template_node_uid': 'uid3'
                }
            ],
            'variables': [],
        }
    }


def test_reparent_nodes(metadata, raw_countrydata):
    cd = CountryData(metadata, raw_countrydata)
    for node, parent_node in cd.reparent_nodes():
        pass
    assert cd.nodes == [
        {
            'name': 'example parent node',
            'uid': 'uid0',
            'template_node_uid' : 'uid1',
            'node': [
                {
                    'name': 'example child node',  # re-parented copy of a child node
                    'uid': 'uid2',
                    'template_node_uid': 'uid3',
                },
            ],
        },
        {
            'uid': 'uid2'  # stripped original of a child node
        }
    ]
