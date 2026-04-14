def test_collect_sector_uids(metadata, uid):
    totals = metadata.nodes[0]
    totals_uid = totals['uid']
    lulucf = totals['node'][3]
    uid0 = uid()
    uid1 = uid()
    lulucf['node'].append({
        'uid': uid0,
        'node': [{
            'uid': uid1
        }]
    })
    filter = metadata.get_sector_filter('lulucf')
    assert metadata.collect_sector_uids(filter) == {
        'nodes': {totals_uid, 'db7b9be0-76bc-497e-a4ee-9334ec2429d2', uid0, uid1},
        'variables': {'de6fab87-82f6-46d5-b8f5-73190d8e4ace'},
        'dimension_instances': {'db7b9be0-76bc-497e-a4ee-9334ec2429d2'},
    }


def test_is_calculated_variable(metadata):
    # regular calculated variable
    variable = metadata.get_variable('fa3ccf38-222e-497a-bda3-3340add925ae')
    node = metadata.get_node(variable['node_uid'])
    assert node['type'] == 'FIXED'
    assert metadata.is_calculated_variable(variable)
    # variable "is_calculated", but node type is not "FIXED"
    variable = metadata.get_variable('50b1a92e-62a4-4378-b5d7-006be67349fa')
    node = metadata.get_node(variable['node_uid'])
    assert node['type'] != 'FIXED'
    assert not metadata.is_calculated_variable(variable)
