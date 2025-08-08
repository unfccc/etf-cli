from collections import deque
import functools
import gc
import io
import json
import logging
import os
import re

from .util import pairwise, pformat_size


logger = logging.getLogger(__name__)


class JSONTreeRoot(dict):
    pass


class JSONTreeWalker:

    _parents = {}  # no weakref support for dict() and list()

    @classmethod
    def _cache_parent(cls, item, parent):
        cls._parents[id(item)] = parent

    @classmethod
    def _cached_parent(cls, item):
        return cls._parents.get(id(item))

    @staticmethod
    def is_json_container(item):
        return isinstance(item, (dict, list))

    @staticmethod
    def is_object(item):
        return isinstance(item, dict)

    @staticmethod
    def _iter_json_children(container):
        if isinstance(container, dict):
            return container.items()
        if isinstance(container, list):
            return enumerate(container)
        type_ = type(container)
        raise ValueError(f'unsupported JSON container type {type_}')

    @classmethod
    def _walk_up(cls, item):
        if (parent := cls._cached_parent(item)):
            yield parent
            return
        locals_ = locals()
        for parent in gc.get_referrers(item):
            if parent is not locals_ \
                    and parent is not cls._parents \
                    and cls.is_json_container(parent):
                yield parent

    @classmethod
    def _walk_down(cls, item):
        # reversed() is significant for stable traversal order:
        # _traverse_graph() appends children to the right of the queue,
        # so the first child should be yielded last
        for (_, child) in reversed(list(cls._iter_json_children(item))):
            if cls.is_json_container(child):
                yield child
                cls._cache_parent(child, item)

    @staticmethod
    def _traverse_graph(start_item, neighbour_func):
        queue = deque([(start_item,)])
        visited = set()
        while queue:
            (item, *_) = chain = queue.pop()
            if id(item) in visited:
                continue
            visited.add(id(item))
            yield chain
            queue.extend(
                (neighbour,) + chain for neighbour in neighbour_func(item)
            )

    @classmethod
    def _get_json_key(cls, parent, child):
        if isinstance(parent, dict):
            key = next(
                key for (key, value) in parent.items() if value is child
            )
            return f'.{key}'
        if isinstance(parent, list):
            index = parent.index(child)
            return f'[{index}]'
        type_ = type(parent)
        raise ValueError(f'unsupported JSON container type {type_}')

    @classmethod
    def parents(cls, item):
        for chain in cls._traverse_graph(item, cls._walk_up):
            topmost = chain[0]
            if isinstance(topmost, JSONTreeRoot):
                for (parent, child) in pairwise(chain):
                    cls._cache_parent(child, parent)
                return chain[:-1]
        return None

    @classmethod
    def traverse(cls, start):
        if not cls.is_json_container(start):
            return
        for (item, *_) in cls._traverse_graph(start, cls._walk_down):
            if cls.is_object(item):
                yield item

    @classmethod
    def json_path(cls, item):
        parents = cls.parents(item)
        return ''.join(
            cls._get_json_key(parent, child)
            for parent, child in pairwise(parents + (item,))
        ) if parents else '<broken_json_path>'

    json_keys = re.compile(r'\.?(\w+)|\[(\d+)\]')

    @classmethod
    def parse_json_path(cls, path):
        result = []
        for key, index in cls.json_keys.findall(path):
            if key:
                result.append(key)
            elif index:
                result.append(int(index))
        return result


class JSONTree(JSONTreeWalker):

    def __init__(self, data):
        if isinstance(data, io.IOBase) or (
            # handle pytest on Windows, which passes tempfile._TemporaryFileWrapper,
            # which is not io.IOBase
            hasattr(data, 'read') and callable(data.read)
        ):
            data = self.from_json_file(data)
        self.tree = JSONTreeRoot(data)

    @staticmethod
    def from_json_file(input_file):
        try:
            size = pformat_size(os.fstat(input_file.fileno()).st_size)
            logger.info('loading %s, size %s', input_file.name, size)
        except io.UnsupportedOperation:
            # unit test, ignore
            pass
        try:
            return json.load(input_file)
        except (json.decoder.JSONDecodeError, UnicodeDecodeError) as exc:
            # handle known cases of wrong encoding:
            # 1. Windows opens texts with sys.getdefaultencoding() == 'cp1252',
            # 2. BOM mark added into beginning of JSON file
            # both cases are well handled by json binary decoder
            with open(input_file.name, 'rb') as input_fallback:
                return json.load(input_fallback)
        finally:
            logger.debug('(meta)data loading complete')

    def __getitem__(self, key):
        return self.tree[key]

    @functools.cache
    def locate(self, path):
        item = self.tree
        for key in self.parse_json_path(path):
            try:
                item = item[key]
            except (IndexError, KeyError):
                return None
        return item

    def dump(self, *args, **kwargs):
        if not kwargs.get('indend'):
            kwargs['indent'] = 4
        return json.dump(self.tree, *args, **kwargs)

    @classmethod
    def collect_uids(cls, item):
        uids = {child.get('uid') for child in cls.traverse(item)}
        for parent in cls.parents(item):
            if cls.is_object(parent):
                uids.add(parent.get('uid'))
        return uids - {None}


NOT_PRESENT = object()  # marker of absent value


class JSONCatalog:

    def __init__(self, indexes, data=None):
        self.items = {}
        self.indexes = {attr: {} for attr in indexes}
        self.values = {}
        if data is not None:
            self.index_iterable(data)

    def clear(self):
        self.items.clear()
        for index in self.indexes.values():
            index.clear()
        self.values.clear()

    def index_iterable(self, data):
        for item in data:
            self.index(item)

    def index(self, item):
        object_id = id(item)
        if object_id in self.items:
            self.unindex(item)
        self.items[object_id] = item
        values = self.values.setdefault(object_id, {})
        for attr, index in self.indexes.items():
            value = item.get(attr, NOT_PRESENT)
            if value is not NOT_PRESENT:
                object_ids = index.setdefault(value, set())
                object_ids.add(object_id)
                values[attr] = value

    def unindex(self, item):
        object_id = id(item)
        if object_id not in self.items:
            return
        for attr, value in self.values[object_id].items():
            self.indexes[attr][value].discard(object_id)
            if not self.indexes[attr][value]:
                del self.indexes[attr][value]
        del self.values[object_id]
        del self.items[object_id]

    def search(self, **criteria):
        result = None
        for attr, value in criteria.items():
            object_ids = self.indexes[attr].get(value, None)
            if not object_ids:
                return []
            result = object_ids if result is None \
                else result.intersection(object_ids)
            if not result:
                return []
        return [] if result is None \
            else [self.items[object_id] for object_id in result]

    def first(self, **criteria):
        """Return first item matching given criteria or None.
        Consume items from data iterator if needed,
        stop iteration on first match."""
        items = self.search(**criteria)
        if items:
            return items[0]

    def one(self, **criteria):
        items = self.search(**criteria)
        if len(items) < 1:
            raise ValueError(
                f'No items have been found matching criteria {criteria}'
            )
        if len(items) > 1:
            raise ValueError(f'Multiple ({len(items)}) items have been found '
                             f'matching criteria {criteria}')
        return items[0]
