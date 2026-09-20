"""Builds little-endian Berkeley DB btree files and UFT object repositories."""
import struct

PAGE = 512
HEADER = 26
META, INTERNAL, LEAF, OVERFLOW = 9, 3, 5, 7


def _page(number, page_type, payload=b"", entries=0, prev=0, next_page=0, hf_offset=0, level=1):
    head = (b"\x00" * 8 + struct.pack("<III", number, prev, next_page)
            + struct.pack("<HHBB", entries, hf_offset, level, page_type))
    return (head + payload).ljust(PAGE, b"\x00")


def _meta_page(number, root):
    head = (b"\x00" * 12 + struct.pack("<III", 0x053162, 9, PAGE)
            + b"\x00" * 4 + struct.pack("<II", 0, 0))
    page = (head + b"\x00" * (PAGE - len(head)))[:PAGE]
    page = bytearray(page)
    page[8:12] = struct.pack("<I", number)
    page[25] = META
    page[88:92] = struct.pack("<I", root)
    return bytes(page)


def _leaf_page(number, items, overflow_pages):
    """items: list of (key, value) already encoded as on-page or overflow entries."""
    body = bytearray(PAGE)
    offsets, cursor = [], PAGE
    entries = [entry for pair in items for entry in pair]
    for entry in entries:
        cursor -= len(entry)
        body[cursor:cursor + len(entry)] = entry
        offsets.append(cursor)
    index = b"".join(struct.pack("<H", offset) for offset in offsets)
    page = bytearray(_page(number, LEAF, index, entries=len(entries), hf_offset=cursor))
    page[cursor:PAGE] = body[cursor:PAGE]
    return bytes(page)


def _keydata(data: bytes) -> bytes:
    return struct.pack("<HB", len(data), 1) + data


def _overflow_ref(first_page: int, total: int) -> bytes:
    return struct.pack("<HBB", 0, 3, 0) + struct.pack("<II", first_page, total)


def btree_file(databases: dict[str, dict[bytes, bytes]], multi=True) -> bytes:
    """databases: name -> records. With multi=False a single unnamed database is written."""
    pages: list[bytes] = [b""]  # master meta page, filled in last
    # Small enough that every fixture leaf page fits; larger values go to overflow pages.
    payload_limit = 64

    def store(records, base):
        items, extra = [], []
        for key, value in records.items():
            entry = _keydata(value)
            if len(value) > payload_limit:
                start = base + len(extra)
                chunks = [value[i:i + payload_limit] for i in range(0, len(value), payload_limit)]
                for index, chunk in enumerate(chunks):
                    following = start + index + 1 if index + 1 < len(chunks) else 0
                    extra.append((start + index, chunk, following))
                entry = _overflow_ref(start, len(value))
            items.append((_keydata(key), entry))
        return items, extra

    leaves = {}
    for name, records in databases.items():
        items, extra = store(records, len(pages))
        leaf_number = len(pages) + len(extra)
        for number, chunk, following in extra:
            pages.append(_page(number, OVERFLOW, chunk, next_page=following, hf_offset=len(chunk), level=0))
        pages.append(_leaf_page(leaf_number, items, extra))
        leaves[name] = leaf_number

    if multi:
        master = {}
        for name, leaf in leaves.items():
            meta_number = len(pages)
            pages.append(_meta_page(meta_number, leaf))
            master[name.encode("latin-1")] = struct.pack(">I", meta_number)
        items, _ = store(master, len(pages))
        master_leaf = len(pages)
        pages.append(_leaf_page(master_leaf, items, []))
        pages[0] = _meta_page(0, master_leaf)
    else:
        pages[0] = _meta_page(0, next(iter(leaves.values())))
    return b"".join(pages)


def _stream(body: bytes) -> bytes:
    return b"\xff\x01" + b"\x00" * 0x1e + struct.pack("<I", len(body)) + b"\x00" * 0x10 + body + b"stale data"


def _text(value: str) -> bytes:
    raw = (value + "\x00").encode("utf-16-le")
    return struct.pack("<I", len(raw)) + raw


def index_stream(entries) -> bytes:
    """entries: nested (group_class, [(name, id, class, children)]) tuples."""
    def children(groups):
        out = b""
        for group, objects in groups:
            out += _text(group) + b"\xcd\xcd\x04\x00"
            for name, object_id, object_class, nested in objects:
                out += _text(name) + _text(object_id) + _text(object_class) + children(nested)
            out += _text("@@End@@")
        return out + _text("@@End@@")
    return _stream(children(entries))


VT_BSTR, VT_I4, VT_BOOL = 8, 3, 11


def object_stream(properties, mandatory=(), assistive=()) -> bytes:
    body = b"\x00" * 0x10 + struct.pack("<I", len(properties))
    names = [name for name, _, _ in properties]
    for name, variant, value in properties:
        body += _text(name)[:4] + (name + "\x00").encode("utf-16-le") + b"\x00" * 4
        body += struct.pack("<H", variant)
        if variant == VT_BSTR:
            raw = (str(value) + "\x00").encode("utf-16-le")
            body += struct.pack("<I", len(raw)) + raw
        elif variant == VT_I4:
            body += struct.pack("<i", value)
        else:
            body += struct.pack("<h", 1 if value else 0)
        body += b"\x00\x01\x00\x01"
    for group in (mandatory, assistive):
        indexes = [names.index(name) for name in group]
        body += struct.pack("<I", len(indexes)) + b"".join(struct.pack("<I", i) for i in indexes)
    return _stream(body)


def object_repository(tree, objects, storage="AAAA1111-0000-0000-0000-000000000001") -> bytes:
    """tree: index_stream entries; objects: id -> object_stream bytes."""
    index_records = {"Inedex".encode("utf-16-le"): index_stream(tree)}
    object_records = {key.encode("utf-16-le"): value for key, value in objects.items()}
    parent = "BBBB2222-0000-0000-0000-000000000002"
    containment = {_guid(parent): _guid(storage)}
    return btree_file({storage: index_records, parent: object_records,
                       "StgContainmentTable": containment})


def _guid(value: str) -> bytes:
    import uuid
    return uuid.UUID(value).bytes_le
