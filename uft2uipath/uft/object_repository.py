"""Parses a UFT local Object Repository (ObjectRepository.bdb).

The Berkeley DB file emulates OLE structured storage: one sub-database holds
the streams "Inedex" (object tree) and one stream per object, keyed by the
object's id (UTF-16). Every stream value starts with a 0x34-byte header whose
uint32 at 0x20 is the stream size; bytes past that size are stale.

Inedex is a sequence of length-prefixed UTF-16 strings (uint32 byte length
including the NUL) separated by binary metadata:
    children := group* "@@End@@"
    group    := GROUP_CLASS object* "@@End@@"
    object   := LOGICAL_NAME ID CLASS children

An object stream holds, from offset 0x10: uint32 property count; per property
uint32 name length, UTF-16 name, 4 reserved bytes, uint16 VARIANT type, value,
4 flag bytes; then two uint32-counted index lists: the mandatory
(identification) properties and the assistive ones.
"""

from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass, field
from typing import Any

from uft2uipath.uft.berkeley_db import BerkeleyDbError, read_databases

INDEX_STREAM = "Inedex"
CONTAINMENT = "StgContainmentTable"
END = "@@End@@"
CHECKPOINT_CLASSES = {"VerifyObj"}
_STREAM_HEADER = 0x34
_PROPERTIES = 0x10
_VT_EMPTY, _VT_I2, _VT_I4, _VT_BSTR, _VT_BOOL, _VT_UI4, _VT_BYTES = 0, 2, 3, 8, 11, 19, 0x2011


class ObjectRepositoryError(ValueError):
    pass


@dataclass
class RepositoryProperty:
    name: str
    value: Any
    variant_type: int
    flags: str


@dataclass
class RepositoryObject:
    id: str
    test_object_class: str
    logical_name: str
    path: list[tuple[str, str]]
    properties: list[RepositoryProperty] = field(default_factory=list)
    mandatory: list[str] = field(default_factory=list)
    assistive: list[str] = field(default_factory=list)
    issue: str | None = None

    def value(self, name: str) -> Any:
        wanted = name.casefold()
        for prop in self.properties:
            if prop.name.casefold() == wanted:
                return prop.value
        return None


@dataclass
class ObjectRepository:
    objects: list[RepositoryObject]

    def find(self, path: list[tuple[str, str]]) -> RepositoryObject | None:
        wanted = [(cls.casefold(), name.casefold()) for cls, name in path]
        for obj in self.objects:
            if [(cls.casefold(), name.casefold()) for cls, name in obj.path] == wanted:
                return obj
        return None


def read_object_repository(data: bytes) -> ObjectRepository:
    try:
        databases = read_databases(data)
    except BerkeleyDbError as exc:
        raise ObjectRepositoryError(str(exc)) from None
    index_key = INDEX_STREAM.encode("utf-16-le")
    index_storages = [name for name, records in databases.items() if index_key in records]
    if len(index_storages) != 1:
        raise ObjectRepositoryError(f"Expected one object index stream, found {len(index_storages)}.")
    index_storage = index_storages[0]
    tree = _parse_index(_strings(_stream(databases[index_storage][index_key])))
    parent = _parent_storage(databases, index_storage)
    objects = []
    for node in tree:
        obj = RepositoryObject(node["id"], node["class"], node["name"], node["path"])
        raw = _object_stream(databases, parent, index_storage, node["id"].encode("utf-16-le"))
        if node["class"] in CHECKPOINT_CLASSES:
            obj.issue = "checkpoint"
        elif raw is None:
            obj.issue = "missing_object_stream"
        else:
            try:
                obj.properties, obj.mandatory, obj.assistive = _parse_object(_stream(raw))
            except (ObjectRepositoryError, struct.error, UnicodeDecodeError) as exc:
                obj.issue = f"unreadable_object: {exc}"
        objects.append(obj)
    return ObjectRepository(objects)


def _parent_storage(databases, child: str) -> str | None:
    # StgContainmentTable maps parent storage GUID -> child storage GUID (16-byte, little-endian layout).
    for parent, value in databases.get(CONTAINMENT, {}).items():
        if len(parent) == 16 and len(value) == 16 and _guid(value) == child.upper():
            return _guid(parent)
    return None


def _object_stream(databases, parent: str | None, index_storage: str, key: bytes) -> bytes | None:
    if parent in databases and key in databases[parent]:
        return databases[parent][key]
    holders = [name for name, records in databases.items()
               if name not in (index_storage, CONTAINMENT) and key in records]
    return databases[holders[0]][key] if len(holders) == 1 else None


def _guid(raw: bytes) -> str:
    return str(uuid.UUID(bytes_le=raw)).upper()


def _stream(value: bytes) -> bytes:
    if len(value) < _STREAM_HEADER or value[:2] != b"\xff\x01":
        raise ObjectRepositoryError("Unknown stream header.")
    size = struct.unpack("<I", value[0x20:0x24])[0]
    if _STREAM_HEADER + size > len(value):
        raise ObjectRepositoryError("Stream is truncated.")
    return value[_STREAM_HEADER:_STREAM_HEADER + size]


def _strings(data: bytes) -> list[str]:
    tokens, position = [], 0
    while position + 4 <= len(data):
        length = struct.unpack("<I", data[position:position + 4])[0]
        end = position + 4 + length
        if 4 <= length <= 2048 and length % 2 == 0 and end <= len(data) and data[end - 2:end] == b"\x00\x00":
            try:
                text = data[position + 4:end - 2].decode("utf-16-le")
            except UnicodeDecodeError:
                text = ""
            if text and all(ch >= " " for ch in text):
                tokens.append(text)
                position = end
                continue
        position += 1
    return tokens


def _parse_index(tokens: list[str]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    position = 0

    def take() -> str:
        nonlocal position
        if position >= len(tokens):
            raise ObjectRepositoryError("Object index ends unexpectedly.")
        position += 1
        return tokens[position - 1]

    def children(path: list[tuple[str, str]]) -> None:
        while (group := take()) != END:
            while (name := take()) != END:
                object_id, object_class = take(), take()
                if END in (object_id, object_class):
                    raise ObjectRepositoryError(f"Malformed object entry {name!r} in group {group!r}.")
                node_path = path + [(object_class, name)]
                nodes.append({"id": object_id, "class": object_class, "name": name, "path": node_path})
                children(node_path)

    while position < len(tokens):
        children([])
    return nodes


def _parse_object(data: bytes) -> tuple[list[RepositoryProperty], list[str], list[str]]:
    position = _PROPERTIES
    count = struct.unpack("<I", data[position:position + 4])[0]
    position += 4
    properties = []
    for _ in range(count):
        length = struct.unpack("<I", data[position:position + 4])[0]
        name = data[position + 4:position + 4 + length].decode("utf-16-le").rstrip("\x00")
        position += 4 + length + 4
        variant = struct.unpack("<H", data[position:position + 2])[0]
        position += 2
        value, position = _variant(data, position, variant)
        flags = data[position:position + 4].hex()
        position += 4
        properties.append(RepositoryProperty(name, value, variant, flags))
    lists = []
    for _ in range(2):
        size = struct.unpack("<I", data[position:position + 4])[0]
        indexes = struct.unpack(f"<{size}I", data[position + 4:position + 4 + 4 * size])
        position += 4 + 4 * size
        if any(index >= count for index in indexes):
            raise ObjectRepositoryError("Identification index out of range.")
        lists.append([properties[index].name for index in indexes])
    return properties, lists[0], lists[1]


def _variant(data: bytes, position: int, variant: int) -> tuple[Any, int]:
    if variant == _VT_BSTR:
        length = struct.unpack("<I", data[position:position + 4])[0]
        return data[position + 4:position + 4 + length].decode("utf-16-le").rstrip("\x00"), position + 4 + length
    if variant in (_VT_I4, _VT_UI4):
        return struct.unpack("<i", data[position:position + 4])[0], position + 4
    if variant == _VT_I2:
        return struct.unpack("<h", data[position:position + 2])[0], position + 2
    if variant == _VT_BOOL:
        return struct.unpack("<h", data[position:position + 2])[0] != 0, position + 2
    if variant == _VT_BYTES:
        length = struct.unpack("<I", data[position:position + 4])[0]
        return data[position + 4:position + 4 + length].hex(), position + 4 + length
    if variant == _VT_EMPTY:
        return None, position + 6
    raise ObjectRepositoryError(f"Unsupported property type {variant}.")
