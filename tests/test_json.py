import copy
import json
import pytest
import sys
import tempfile
from unittest import mock

from unfccc.etf.json import JSONCatalog, JSONTree
from unfccc.etf.util import pairwise


@pytest.fixture
def catalog():
    return JSONCatalog(
        ['uid', 'parent_uid', 'template_node_uid', 'name', 'name_prefix']
    )


@pytest.fixture
def country_specific_nodes(nodes, parent_uid):
    # form a "data file" tree, bound with 'parent_uid' references
    rv = copy.deepcopy(nodes)[0]['node']
    rv[1]['parent_uid'] = rv[3]['parent_uid'] = rv[4]['parent_uid'] = \
        parent_uid
    return rv


def test_pairwise():
    data = list(range(5))
    assert list(pairwise(data)) == [(0, 1), (1, 2), (2, 3), (3, 4)]


def test_jsontree_from_object(raw_metadata):
    metadata = JSONTree(raw_metadata)
    assert metadata.tree == raw_metadata


def test_jsontree_from_file(raw_metadata):
    with tempfile.TemporaryFile('w+t') as json_file:
        json.dump(raw_metadata, json_file)
        json_file.seek(0)
        metadata = JSONTree(json_file)
    assert metadata.tree == raw_metadata


def test_parents(raw_metadata):
    metadata = JSONTree(raw_metadata)
    root = metadata['Metadata']
    metadata_singleton = root[0]
    nodes = metadata_singleton['node']
    totals = nodes[0]
    sectors = totals['node']
    lulucf = sectors[3]
    parents = metadata.parents(lulucf)
    assert parents == (metadata.tree, root, metadata_singleton, nodes, totals, sectors)


def test_json_path(raw_metadata):
    metadata = JSONTree(raw_metadata)
    item = metadata['Metadata'][0]['node'][0]['node'][3]
    assert metadata.json_path(item) == '.Metadata[0].node[0].node[3]'


def test_locate(raw_metadata):
    metadata = JSONTree(raw_metadata)
    item = metadata['Metadata'][0]['node'][0]['node'][3]
    assert metadata.locate('.Metadata[0].node[0].node[3]') is item
    assert metadata.locate('.Metadata[0].wrong_key') is None


def test_traverse(raw_metadata):
    metadata = JSONTree(raw_metadata)
    nodes = metadata['Metadata'][0]['node'][0]['node']
    for index, item in enumerate(metadata.traverse(nodes)):
        pass
    assert item is nodes[-1]


def test_catalog_reindex(catalog, metadata_node):
    catalog.index(metadata_node)
    object_id = id(metadata_node)
    assert catalog.indexes == {
        'uid': {
            metadata_node['uid']: {object_id},
        },
        'parent_uid': {},
        'template_node_uid': {
            None: {object_id}
        },
        'name': {
            'Energy': {object_id},
        },
        'name_prefix': {
            '1.': {object_id},
        },
    }
    assert catalog.items[object_id] is metadata_node
    # check unindexing
    catalog.unindex(metadata_node)
    assert catalog.indexes == {
        'uid': {},
        'parent_uid': {},
        'template_node_uid': {},
        'name': {},
        'name_prefix': {}
    }


def test_catalog_search(catalog, metadata_node, country_specific_nodes,
                        parent_uid):
    # check empty catalog
    catalog.clear()
    assert catalog.search(parent_uid=parent_uid) == []
    # check catalog with one non-matching object
    catalog.index(metadata_node)
    assert catalog.search(parent_uid=parent_uid) == []
    # check catalog with matching object
    node = metadata_node.copy()
    node['parent_uid'] = parent_uid
    catalog.index(node)
    assert catalog.search(parent_uid=parent_uid) == [node]
    catalog.unindex(node)
    # check matching in multiple items
    nodes = country_specific_nodes
    catalog.index_iterable(nodes)
    assert catalog.search(uid=nodes[1]['uid']) == [nodes[1]]
    assert catalog.search(name='Agriculture') == [nodes[2]]
    assert catalog.search(name='cannot be found') == []
    items = catalog.search(parent_uid=parent_uid)
    assert len(items) == 3
    for node in [nodes[1], nodes[3], nodes[4]]:
        assert node in items
    template_node_uid = nodes[4]['template_node_uid']
    assert catalog.search(parent_uid=parent_uid,
                          template_node_uid=template_node_uid) == [nodes[4]]


def test_catalof_get(catalog, country_specific_nodes, parent_uid):
    nodes = country_specific_nodes
    catalog.index_iterable(nodes)
    uid = nodes[3]['uid']
    assert catalog.first(uid=uid) == nodes[3]
    try:
        catalog.one(parent_uid=parent_uid)
    except ValueError as exc:
        assert 'Multiple' in exc.args[0]
    else:
        assert False, 'ValueError has not been raised'


def test_load_utf8_on_windows(raw_metadata, tmp_path):
    raw_metadata['test_key'] = 'non-ascii: ' + b'\xe2\x82\x81'.decode('utf-8')
    source = json.dumps(raw_metadata, ensure_ascii=False)
    wrong_encoding = 'cp1252'
    with mock.patch('sys.getdefaultencoding', return_value=wrong_encoding):
        assert sys.getdefaultencoding() == wrong_encoding
        metadata_path = tmp_path / 'metadata.json'
        metadata_path.write_bytes(source.encode('utf-8'))
        with metadata_path.open('rt', encoding=wrong_encoding ) as input_file:
            metadata = JSONTree(input_file)
