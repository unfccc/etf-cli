import functools
from importlib.resources import path as resource_path
import logging
import lzma
import re
from uuid import UUID

from .json import JSONTree, JSONCatalog


logger = logging.getLogger(__name__)


def is_uuid4(value):
    try:
        UUID(value, version=4)
    except ValueError:
        return False
    return True


class Metadata(JSONTree):

    def __init__(self, data):
        if data is None:
            # no metadata file given, read the bundled one
            with resource_path(__package__ + '.assets',
                               'metadata.json.lzma') as bundled_metadata_path:
                # lzma gives the best compression vs gzip, bzip2, zip
                data = lzma.LZMAFile(bundled_metadata_path, 'rb')
                if not hasattr(data, 'name'):
                    data.name = 'bundled metadata.json.lzma'
        super().__init__(data)
        self.debug_version()
        self.node_index = JSONCatalog(
            ['uid', 'parent_uid', 'template_node_uid', 'name_prefix', 'name'],
            self.traverse(self.nodes)
        )
        self.dimension_instance_index = JSONCatalog(
            ['uid', 'name'], self.traverse(self.navigation_root)
        )
        self.grid_index = JSONCatalog(['node_uid'], iter(self.grids))
        self.variable_index = JSONCatalog(['id', 'uid'], iter(self.variables))

    def debug_version(self):
        if version := self.root.get('version'):
            for key, label in [
                ('name', 'version'), ('version', 'version ID'),
                ('publication_date', 'published')
            ]:
                logger.debug('Metadata %s: %s', label, version[key])

    @functools.cached_property
    def root(self):
        return self.tree['Metadata'][0]

    @functools.cached_property
    def dimensions(self):
        return self.root['dimension']

    @functools.cached_property
    def dimension_instances(self):
        return self.root['dimension_instance']

    @functools.cached_property
    def variables(self):
        return self.root['variable']

    @functools.cached_property
    def grids(self):
        return self.root['grid']

    @functools.cached_property
    def nodes(self):
        return self.root['node']

    @functools.cached_property
    def navigation_dimension(self):
        for dimension in self.dimensions:
            if dimension['name'] == 'NAVIGATION':
                return dimension
        return None

    @functools.cached_property
    def navigation_root(self):
        for instance in self.dimension_instances:
            if instance['dimension_id'] == self.navigation_dimension['id']:
                return instance
        return None

    sector_uids = {
        'energy': '3665c27e-d055-47d7-8393-5f934f3ced9d',
        'ippu': 'fed65b84-cdad-4e38-8848-ea6af3c391bc',
        'lulucf': 'db7b9be0-76bc-497e-a4ee-9334ec2429d2',
        'agriculture': '43bc1534-201c-416b-a348-e5866d69dddb',
        'waste': 'b1e41219-79a2-493d-ba97-de0e4d7f9d0f',
        'docbox': 'bd942384-e7cd-4280-bf40-a010a549f245',
        'other': 'b5cf62a9-7dff-4330-bbb1-619f1aeddfb4',
        'totals': '711ab9da-13cd-44d8-b8f4-33a954171186'
    }

    def get_sector_filter(self, name):
        if is_uuid4(name):
            return {'uid': name}
        uid = self.sector_uids.get(name.lower())
        if uid is not None:
            logger.debug('sector alias "%s" translated to uid "%s"', name, uid)
            return {'uid': uid}
        return {'name': name}

    def find_navigation_dis(self, filter_):
        yield from self.dimension_instance_index.search(**filter_)

    def find_nodes(self, filter_):
        name = filter_.get('name')
        prefixed_category_name = re.compile(
            r'[\w.]+\.\s+\w+'
        )
        if name is not None and prefixed_category_name.match(name):
            prefix, name = name.split(' ', 1)
            logger.debug('searching for unprefixed node name "%s"', name)
            filter_ = dict(filter_, name=name, name_prefix=prefix)
        yield from self.node_index.search(**filter_)

    def get_node(self, uid):
        return self.node_index.first(uid=uid)

    def get_grid(self, node_uid):
        return self.grid_index.first(node_uid=node_uid)

    def get_variable(self, uid):
        return self.variable_index.first(uid=uid)

    def is_calculated_variable(self, variable):
        if not variable['is_calculated']:
            return False
        node = self.get_node(variable['node_uid'])
        return node['type'] == 'FIXED'

    def collect_sector_uids(self, filter_):
        result = {
            'nodes': set(),
            'variables': set(),
            'dimension_instances': set()
        }
        sector_uids = result['nodes']
        for node in self.find_nodes(filter_):
            path = self.json_path(node)
            logger.debug('found node with uid = "%s" at "%s"',
                         node["uid"], path)
            sector_uids.update(self.collect_uids(node))
        logger.debug('collected %s node uids', len(sector_uids))
        sector_uids = result['dimension_instances']
        for dimension_instance in self.find_navigation_dis(filter_):
            path = self.json_path(dimension_instance)
            logger.debug('found dimension instance with uid = "%s" at "%s"',
                         dimension_instance["uid"], path)
            sector_uids.update(self.collect_uids(dimension_instance))
        logger.debug('collected %s dimension instance uids', len(sector_uids))
        sector_uids = result['variables']
        for variable in self.variables:
            if variable.get('node_uid') in result['nodes']:
                sector_uids.add(variable['uid'])
        logger.debug('collected %s variable uids', len(sector_uids))
        return result
