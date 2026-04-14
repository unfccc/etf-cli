import pytest
import uuid

from unfccc.etf.metadata import Metadata


@pytest.fixture
def uid():
    return lambda: str(uuid.uuid4())


@pytest.fixture
def parent_uid(uid):
    return uid()


@pytest.fixture
def metadata_node():
    return {
        'uid': '3665c27e-d055-47d7-8393-5f934f3ced9d',
        'name_prefix': '1.',
        'name': 'Energy',
        'template_node_uid': None,
    }


@pytest.fixture
def nodes(metadata_node, parent_uid, uid):
    return [
        {
            'uid': '711ab9da-13cd-44d8-b8f4-33a954171186',
            'name': 'Sectors/Totals',
            'node': [
                metadata_node,
                {
                    'uid': 'fed65b84-cdad-4e38-8848-ea6af3c391bc',
                    'name_prefix': '2.',
                    'name': 'Industrial processes and product use',
                    'node': [
                        {
                            'uid': '5c9bfccc-9526-45b7-8341-7e9ec30236a9',
                            'name_prefix': '2.B.',
                            'name': 'Chemical industry',
                            'type': 'FIXED',
                            'node': [
                                {
                                    'uid': '39943dcd-86a4-4631-b294-37ef3b8a7fb6',
                                    'name_prefix': '2.B.7.',
                                    'name': 'Soda ash production',
                                    'type': 'FIXED',
                                }
                            ]
                        },
                        {
                            'uid': '3e4000d3-8f9d-4f6a-8d86-2fb4c8a7f99d',
                            'name_prefix': '2.G.',
                            'name': 'Other product manufacture and use',
                            'type': 'FIXED',
                            'node': [
                                {
                                    'uid': '0e959739-e2b8-4913-9f21-fe5eaa804c2d',
                                    'name_prefix': '2.G.2.',
                                    'name': 'SF₆ and PFCs from other product use',
                                    'type': 'FIXED',
                                    'node': [
                                        {
                                            'uid': 'bbf45eca-6575-4172-b26d-a62ea455e47c',
                                            'name_prefix': '2.G.2.b.',
                                            'name': 'Accelerators',
                                            'type': 'LIST',
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    'uid': '43bc1534-201c-416b-a348-e5866d69dddb',
                    'name_prefix': '3.',
                    'name': 'Agriculture',
                    'template_node_uid': uid(),
                    'node': []
                },
                {
                    'uid': 'db7b9be0-76bc-497e-a4ee-9334ec2429d2',
                    'name_prefix': '4.',
                    'name': 'Land use, land-use change and forestry',
                    'template_node_uid': uid(),
                    'node': []
                },
                {
                    'uid': 'b1e41219-79a2-493d-ba97-de0e4d7f9d0f',
                    'name_prefix': '5.',
                    'name': 'Waste',
                    'parent_uid': None,
                    'template_node_uid': uid(),
                    'node': []
                }
            ]
        },
    ]


@pytest.fixture
def raw_metadata(nodes):
    # truncated copy of a real production ETF metadata definition
    return {
        'Metadata': [
            {
                'node': nodes,
                'dimension': [
                    {
                        'id': 1,
                        'name': 'NAVIGATION'
                    }
                ],
                'dimension_instance': [
                    {
                        'dimension_id': 1,
                        'id': 301,
                        'uid': 'db7b9be0-76bc-497e-a4ee-9334ec2429d2',
                        'name': '4. Land use, land-use change and forestry',
                        'children': []
                    }
                ],
                'grid': [],
                'variable': [
                    {
                        'uid': '50b1a92e-62a4-4378-b5d7-006be67349fa',
                        'name': '[2.G.2.b. Accelerators][no classification][Emissions][PFCs][no parameter][t CO₂ equivalent]',
                        'is_calculated': True,
                        'node_uid': 'bbf45eca-6575-4172-b26d-a62ea455e47c',
                    },
                    {
                        'uid': 'fa3ccf38-222e-497a-bda3-3340add925ae',
                        'node_uid': '39943dcd-86a4-4631-b294-37ef3b8a7fb6',
                        'name': '[2.B.7. Soda ash production][no classification][Recovery CO₂ fossil][CO₂][no parameter][kt]',
                        'is_calculated': True,
                    },
                    {
                        'uid': 'de6fab87-82f6-46d5-b8f5-73190d8e4ace',
                        'node_uid': 'db7b9be0-76bc-497e-a4ee-9334ec2429d2',
                        'name': '[4. Land use, land-use change and '
                        'forestry][no classification][Emissions]'
                        '[CO₂][no parameter][kt]',
                        'is_calculated': True,
                    }
                ]
            }
        ]
    }


@pytest.fixture
def metadata(raw_metadata):
    return Metadata(raw_metadata)
