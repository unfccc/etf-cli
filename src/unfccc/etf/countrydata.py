from copy import deepcopy
import functools
import logging
import secrets
from functools import partial

from .json import JSONCatalog, JSONTree
from .util import pformat_size, sizeof_dict


logger = logging.getLogger(__name__)


class CountryData(JSONTree):

    stat_points = [
        ('Country specific dimension instances',
         'country_specific_data.dimension_instances'),
        ('Country specific nodes', 'country_specific_data.nodes'),
        ('Country specific variables', 'country_specific_data.variables'),
        ('Country specific grids', 'country_specific_data.grids'),
        ('Country specific drop-downs', 'country_specific_data.drop_downs'),
        ('Country specific line descriptions',
         'country_specific_data.line_description'),
        ('Country specific (meta)data', 'country_specific_data'),
        ('Country data', 'data')
    ]

    def __init__(self, metadata, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metadata = metadata
        self.node_index = JSONCatalog(
            ['uid', 'parent_uid', 'template_node_uid', 'name_prefix', 'name'],
            self.traverse(self.nodes)
        )
        self.variable_index = JSONCatalog(
            ['uid', 'node_uid', 'template_var_uid'],
            self.variables
        )
        self.grid_index = JSONCatalog(['node_uid', 'line_type'],
                                      self.traverse(self.grids))

    @functools.cached_property
    def root(self):
        return self.tree

    @functools.cached_property
    def country_metadata(self):
        return self.root['country_specific_data']

    @functools.cached_property
    def nodes(self):
        return self.country_metadata['nodes']

    @functools.cached_property
    def variables(self):
        return self.country_metadata['variables']

    @functools.cached_property
    def grids(self):
        return self.country_metadata.setdefault('grids', [])

    @functools.cached_property
    def line_descriptions(self):
        return self.country_metadata.setdefault('line_description', [])

    @functools.cached_property
    def data(self):
        return self['data']['values']

    @staticmethod
    def is_metadata_uid(uid):
        return '-' in uid

    @staticmethod
    def is_visibility_reference(node):
        return isinstance(node, dict) and list(node.keys()) == ['uid']

    def get_node(self, uid, fallback_to_metadata=True):
        result = self.node_index.first(uid=uid)
        if result is None and fallback_to_metadata:
            result = self.metadata.get_node(uid)
        return result

    def get_grid(self, node_uid, fallback_to_metadata=True):
        result = self.grid_index.first(node_uid=node_uid)
        if result is None and fallback_to_metadata:
            result = self.metadata.get_grid(node_uid)
        return result

    def collect_sector_uids(self, filter_):
        result = self.metadata.collect_sector_uids(filter_)
        sector_uids = result['nodes']
        old_len = len(sector_uids)
        for node in self.nodes:
            if 'parent_uid' in node and node['parent_uid'] in sector_uids:
                for child in self.traverse(node):
                    sector_uids.add(child['uid'])
        logger.info('collected %s country specific node uids',
                    len(sector_uids) - old_len)
        return result

    @staticmethod
    def filter_out(item_list, filter_func, valid_uids=None):
        to_delete = []
        for index, item in enumerate(item_list):
            if filter_func(item):
                if valid_uids is not None:
                    valid_uids.add(item['uid'])
            else:
                to_delete.append(index)
        for index in reversed(to_delete):
            del item_list[index]
        return to_delete

    @staticmethod
    def make_uid():
        return secrets.token_hex(12)

    def reparent_nodes(self):
        # reparent multi-level nodes into tree structure
        nested_nodes = []
        processed = set()
        for index, node in enumerate(self.nodes):
            if 'template_node_uid' in node and 'parent_uid' in node:
                node_uid = node['uid']
                parent_uid = node['parent_uid']
                template_node_uid = node['template_node_uid']
                if self.is_metadata_uid(node_uid) \
                        or self.is_metadata_uid(parent_uid):
                    continue
                parent_node = self.get_node(parent_uid, False)
                if parent_node is None:
                    logger.error(
                        'node "%s" refers to missing parent node "%s"',
                        node_uid, parent_uid
                    )
                    continue
                yield node, parent_node
                if (parent_uid, template_node_uid) in processed:
                    logger.error('detected duplicate node: template_node_uid="%s", parent_uid="%s"'.
                                 template_node_uid, parent_uid)
                processed.add((parent_uid, template_node_uid))
                del node['parent_uid']
                parent_node.setdefault('node', []).append(deepcopy(node))
                nested_nodes.append(index)
        # cleanup reparented nodes in the root level list and rebuild indexes
        self.node_index.clear()
        for index in reversed(nested_nodes):
            del self.nodes[index]
        self._fix_node_visibility_references()
        self.node_index.index_iterable(self.traverse(self.nodes))

# node visibility reference is a special copy of node
# which retains its UID, and is placed in the root node list,
# and tells ETF Reporter that the node should be shown in the interface,
# example: { "uid": "00000000-0000-0000-0000-000000000000" }
    def _fix_node_visibility_references(self):
        """Move node visibility references to the end of node list
        so that they are processed after the full nodes in the tree,
        """
        # collect UIDs of all nodes in the tree
        all_node_uids = set(
            node['uid'] for node in self.traverse(self.nodes)
        )
        # remove node visibility references from their original places
        noderef_indices = [
            index for (index, node) in enumerate(self.nodes)
            if self.is_visibility_reference(node)
        ]
        for index in reversed(noderef_indices):
            del self.nodes[index]
        # then add node visibility references at the end of the node list,
        # making sure that reference always comes after its original
        for uid in sorted(all_node_uids):
            self.nodes.append({'uid': uid})

    def make_variable(self, node_uid, template_var_uid):
        result = {
            'uid': self.make_uid(),
            'node_uid': node_uid,
            'template_var_uid': template_var_uid
        }
        self.variables.append(result)
        self.variable_index.index(result)
        return result

    def clone_grid_from_template(self, template_node_uid, node_uid):
        result = deepcopy(self.get_grid(template_node_uid))
        result['node_uid'] = node_uid
        for group in self.traverse(result['group']):
            if 'uid' not in group or 'variable_uid' not in group:
                # only traverse nested groups
                continue
            group['template_group_uid'] = group['uid']
            group['uid'] = self.make_uid()
            template_var_uid = group['variable_uid']
            if template_var_uid is None:
                continue
            if group.get('line_type') == 'CROSS_REFERENCE':
                # first create variables in regular groups
                # and then fix cross references later
                group['_temp_node_uid'] = node_uid
                continue
            variable = self.variable_index.first(
                node_uid=node_uid,
                template_var_uid=template_var_uid
            )
            if variable is None:
                logger.debug('adding missing variable "%s" as required by grid "%s"',
                             (node_uid, template_var_uid), template_node_uid)
                variable = self.make_variable(node_uid, template_var_uid)
            group['variable_uid'] = variable['uid']
        return result

    def fix_node_grid(self, node):
        if 'template_node_uid' not in node:
            return
        node_uid = node['uid']
        grid = self.get_grid(node_uid, fallback_to_metadata=False)
        if grid is not None:
            return
        logger.debug('detected country specific node without grid, '
                     'uid="%s", path "%s"', node_uid, self.json_path(node))
        template_node_uid = node['template_node_uid']
        new_grid = self.clone_grid_from_template(template_node_uid, node_uid)
        self.grids.append(new_grid)
        # index new grid with all its groups,
        # so that fix_cross_references() could find them later
        self.grid_index.index_iterable(self.traverse(new_grid))

    def fix_cross_references(self):
        for group in self.grid_index.search(line_type='CROSS_REFERENCE'):
            node_uid = group.pop('_temp_node_uid')
            child_node_uids = set()
            for node in self.node_index.search(uid=node_uid):
                # loop over .search() because there can be two copies of the node:
                # one copy with the full into created by re-parenting fix
                # and another, former original stripped to 'uid' only,
                # they can go in any order, so .first() cannot be used reliably
                if node.get('node'):
                    child_node_uids.update(
                        child_node['uid'] for child_node in self.traverse(node['node'])
                    )
            template_var_uid = group['variable_uid']
            for child_node_uid in child_node_uids:
                variable = self.variable_index.first(
                    node_uid=child_node_uid,
                    template_var_uid=template_var_uid
                )
                if variable is not None:
                    group['variable_uid'] = variable['uid']
                    break
            else:
                root_node_variable = self.variable_index.first(
                    node_uid=node_uid,
                    template_var_uid=template_var_uid
                )
                logger.debug('could not find a variable for CROSS_REFERENCE group "%s", '
                             '%s child nodes checked, root node variable (%s, %s) %s',
                             group['uid'], len(child_node_uids), node_uid, template_var_uid,
                             'exists' if root_node_variable is not None else 'does not exist')
                if root_node_variable is None:
                    logger.debug('adding missing variable "%s" as required by group "%s"',
                                 (node_uid, template_var_uid), group['uid'])
                    root_node_variable = self.make_variable(node_uid, template_var_uid)
                group['variable_uid'] = root_node_variable['uid']

    def count_statistics(self):
        result = []
        for (label, json_path) in self.stat_points:
            item = self.locate(json_path)
            length = index = size = 0
            if item is not None:
                if not self.is_object(item):
                    # JSON array, report also flat length
                    length = len(item)
                for index, child in enumerate(self.traverse(item)):
                    size += sizeof_dict(child)
                index += 1
            result.append({
                'label': label,
                'objects_flat': length,
                'objects_nested': index,
                'size': pformat_size(size)
            })
        return result

    def is_calculated_value(self, value):
        variable_uid = value.get('variable_uid')
        if not variable_uid:
            logger.error('data value without variable UID: %s', self.json_path(value))
            return False
        if not self.is_metadata_uid(variable_uid):
            return False
        variable = self.metadata.get_variable(variable_uid)
        if variable is None:
            logger.error('data value refers to non-existing variable %s: %s', variable_uid, self.json_path(value))
            return False
        return self.metadata.is_calculated_variable(variable)

    def remove_calculated_values(self):

        def is_not_calculated_value(year, value):
            calculated = self.is_calculated_value(value)
            if calculated:
                logger.debug('removing the value of a calculated variable %s / %s', year, value['variable_uid'])
            return not calculated

        for inventory in self.data:
           year = inventory['inventory_year']
           self.filter_out(inventory['values'], partial(is_not_calculated_value, year))
