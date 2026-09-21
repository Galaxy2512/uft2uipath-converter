"""Read-only access to little-endian Berkeley DB btree files (UFT .bdb).

A file may hold several sub-databases: the master database (meta page 0)
maps each sub-database name to its meta page number (4 bytes, big-endian).
Every btree meta page stores its root page number at offset 88.

Page header: lsn(8) pgno(4) prev(4) next(4) entries(2) hf_offset(2) level(1)
type(1). Internal pages (type 3) point to children at item offset +4. Leaf
pages (type 5) hold key/data item pairs; an item is either on-page (len u16,
type 1, bytes) or an overflow reference (type 3, first page u32 at +4, total
length u32 at +8). Overflow pages (type 7) carry hf_offset bytes each.
"""

from __future__ import annotations

import struct

BTREE_MAGIC = 0x053162
INTERNAL_PAGE = 3
LEAF_PAGE = 5
OVERFLOW_PAGE = 7
META_PAGE = 9
KEYDATA = 1
OVERFLOW = 3
DELETED = 0x80
HEADER = 26
ROOT_OFFSET = 88


class BerkeleyDbError(ValueError):
    """The data is not a readable Berkeley DB btree file."""
    pass


def is_berkeley_btree(data: bytes) -> bool:
    """True if the data starts like a little-endian Berkeley DB btree file."""
    return len(data) >= 24 and struct.unpack("<I", data[12:16])[0] == BTREE_MAGIC


def read_databases(data: bytes) -> dict[str, dict[bytes, bytes]]:
    """Returns {sub-database name: records}; plain files map "" to their records."""
    pages = _pages(data)
    master = _tree(pages, 0)
    names = {}
    for key, value in master.items():
        if len(value) == 4:
            number = struct.unpack(">I", value)[0]
            if 0 < number < len(pages) and pages[number][25] == META_PAGE:
                names[key.decode("latin-1")] = number
    if not names:
        return {"": master}
    return {name: _tree(pages, number) for name, number in names.items()}


def _pages(data: bytes) -> list[bytes]:
    """The file split into pages of the size its header states."""
    if not is_berkeley_btree(data):
        raise BerkeleyDbError("Not a little-endian Berkeley DB btree file.")
    page_size = struct.unpack("<I", data[20:24])[0]
    if page_size < 512 or len(data) % page_size:
        raise BerkeleyDbError(f"Invalid page size {page_size} for file of {len(data)} bytes.")
    return [data[i:i + page_size] for i in range(0, len(data), page_size)]


def _tree(pages, meta: int) -> dict[bytes, bytes]:
    """All key/value records of the btree whose meta page is given."""
    root = struct.unpack("<I", pages[meta][ROOT_OFFSET:ROOT_OFFSET + 4])[0]
    records: dict[bytes, bytes] = {}
    pending, seen = [root], set()
    while pending:
        number = pending.pop()
        if number in seen or not 0 < number < len(pages):
            raise BerkeleyDbError(f"Invalid or repeated page {number} in btree.")
        seen.add(number)
        page = pages[number]
        count = struct.unpack("<H", page[20:22])[0]
        offsets = [struct.unpack("<H", page[HEADER + 2 * i:HEADER + 2 * i + 2])[0] for i in range(count)]
        if page[25] == INTERNAL_PAGE:
            # Reversed so the leftmost child is processed first.
            pending.extend(struct.unpack("<I", page[o + 4:o + 8])[0] for o in reversed(offsets))
        elif page[25] == LEAF_PAGE:
            items = [_item(pages, page, offset) for offset in offsets]
            for key, value in zip(items[::2], items[1::2]):
                if key is not None and value is not None:
                    records[key] = value
        else:
            raise BerkeleyDbError(f"Unexpected page type {page[25]} at page {number}.")
    return records


def _item(pages, page: bytes, offset: int) -> bytes | None:
    """Bytes of one on-page or overflow item; None for a deleted item."""
    kind = page[offset + 2]
    if kind & DELETED:
        return None
    if kind == KEYDATA:
        length = struct.unpack("<H", page[offset:offset + 2])[0]
        return page[offset + 3:offset + 3 + length]
    if kind == OVERFLOW:
        number, total = struct.unpack("<II", page[offset + 4:offset + 12])
        return _overflow(pages, number, total)
    raise BerkeleyDbError(f"Unsupported item type {kind}.")


def _overflow(pages, number: int, total: int) -> bytes:
    """Bytes of an item stored across a chain of overflow pages."""
    chunks, size, seen = [], 0, set()
    while number and size < total:
        if number in seen or number >= len(pages) or pages[number][25] != OVERFLOW_PAGE:
            raise BerkeleyDbError(f"Broken overflow chain at page {number}.")
        seen.add(number)
        page = pages[number]
        length = struct.unpack("<H", page[22:24])[0]
        chunks.append(page[HEADER:HEADER + length])
        size += length
        number = struct.unpack("<I", page[16:20])[0]
    data = b"".join(chunks)
    if len(data) < total:
        raise BerkeleyDbError("Overflow item is truncated.")
    return data[:total]
