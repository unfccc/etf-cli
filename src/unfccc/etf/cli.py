#!/usr/bin/env python3
import logging

import click

from .countrydata import CountryData
from .metadata import Metadata
from .util import BiFormatter


logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(BiFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)


pass_metadata = click.make_pass_decorator(Metadata)


@click.group()
@click.option('-v', '--verbose', count=True)
@click.option('-m', '--metadata-file', type=click.File('rb'),
              help='override built-in metadata definition with custom version')
@click.pass_context
def main(ctx, verbose, metadata_file):
    if verbose:
        logger.setLevel(logging.DEBUG)
    ctx.obj = Metadata(metadata_file)


@main.group(help='group of commands for processing ETF metadata files')
def metadata():
    pass


@metadata.command(help='find objects in the ETF metadata file')
@pass_metadata
@click.argument('sector', type=str, required=True)
def find(metadata, sector):
    filter_ = metadata.get_sector_filter(sector)
    logger.info('searching for %s', filter_)
    for node in metadata.find_nodes(filter_):
        path = metadata.json_path(node)
        logger.info('found node with uid = "%s" at "%s"', node["uid"], path)
        for parent in metadata.parents(node):
            if metadata.is_object(parent) and 'name' in parent:
                logger.info('\tsector: %s %s,\n\t\tuid: %s', parent['name_prefix'],
                            parent['name'], parent['uid'])
        logger.info('\tnode: %s %s', node['name_prefix'], node['name'])
    for dimension_instance in metadata.find_navigation_dis(filter_):
        path = metadata.json_path(dimension_instance)
        logger.info('found dimension instance with uid = "%s" at "%s"',
                    dimension_instance["uid"], path)


@main.group(help='group of commands for processing ETF country report files')
def data():
    pass


@data.command(help='output part of data file filtered by sector')
@pass_metadata
@click.option('-s', '--sector', type=str, required=True,
              help='name or UID of navigation node to filter the output')
@click.argument('input_file', type=click.File('rb'),
                default=click.get_text_stream('stdin'))
@click.argument('output_file', type=click.File('w'),
                default=click.get_text_stream('stdout'))
def filter(metadata, sector, input_file, output_file):
    country_data = CountryData(metadata, input_file)
    filter_ = metadata.get_sector_filter(sector)
    sector_uids = country_data.collect_sector_uids(filter_)
    sector_node_uids = sector_uids['nodes']
    # country specific nodes can form the tree,
    # but flat list filtering should still work
    # because if the node /not/ belongs to specified sector
    # then all its children are the same
    deleted = country_data.filter_out(
        country_data.nodes,
        lambda node: (
            node['uid'] in sector_node_uids
            or node.get('parent_uid') in sector_node_uids
            or node.get('template_node_uid') in sector_node_uids
        ),
        sector_node_uids
    )
    logger.info('filtered out %s nodes not belonging to sector "%s"',
                len(deleted), sector)
    sector_variable_uids = sector_uids['variables']
    deleted = country_data.filter_out(
        country_data.variables,
        lambda variable: (
            variable['uid'] in sector_variable_uids
            or variable.get('node_uid') in sector_node_uids
        ),
        sector_variable_uids
    )
    logger.info('filtered out %s variables not belonging to sector "%s"',
                len(deleted), sector)
    deleted = country_data.filter_out(
        country_data.grids,
        lambda grid: grid['node_uid'] in sector_node_uids
    )
    logger.info('filtered out %s grids not belonging to sector "%s"',
                len(deleted), sector)
    deleted = country_data.filter_out(
        country_data.line_descriptions,
        lambda line_desc: line_desc['variable_uid'] in sector_variable_uids
    )
    logger.info('filtered out %s line descriptions '
                'not belonging to sector "%s"', len(deleted), sector)
    for inventory in country_data.data:
        year = inventory['inventory_year']
        deleted = country_data.filter_out(
            inventory['values'],
            lambda value: value['variable_uid'] in sector_variable_uids
        )
        logger.info('filtered out %s data values for year %s '
                    'not belonging to sector "%s"', len(deleted), year, sector)
    country_data.dump(output_file)


@data.command(help='correct errors in data file')
@pass_metadata
@click.option('-r', '--requirements', required=True, multiple=True,
              type=click.Choice(['GRIDS', 'PARENTS', 'CALCULATED', 'ALL']), default=['ALL'],
              help='type(s) of import requirements to satisfy')
@click.argument('input_file', type=click.File('rb'),
                default=click.get_text_stream('stdin'))
@click.argument('output_file', type=click.File('w'),
                default=click.get_text_stream('stdout'))
def fix(metadata, requirements, input_file, output_file):
    country_data = CountryData(metadata, input_file)
    if 'PARENTS' in requirements or 'ALL' in requirements:
        logger.info('transforming node list into tree')
        for node, parent_node in country_data.reparent_nodes():
            logger.debug('moving child node "%s" under parent node "%s"',
                         node['uid'], parent_node['uid'])
    if 'GRIDS' in requirements or 'ALL' in requirements:
        logger.info('adding required template grids')
        for node in country_data.traverse(country_data.nodes):
            if node.get('template_node_uid'):
                country_data.fix_node_grid(node)
    if 'CALCULATED' in requirements or 'ALL' in requirements:
        logger.info('removing data values for calculated variables')
        country_data.remove_calculated_values()
    country_data.dump(output_file)


@data.command(help='output statistics for data file')
@pass_metadata
@click.argument('input_file', type=click.File('rb'),
                default=click.get_text_stream('stdin'))
def stats(metadata, input_file):
    country_data = CountryData(metadata, input_file)
    for stat in country_data.count_statistics():
        logger.info('%(label)s: %(objects_flat)s direct children, '
                    '%(objects_nested)s objects, %(size)s bytes', stat)


if __name__ == '__main__':
    main()
