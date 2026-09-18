"""Reads UFT action metadata from Resource.mtr (OLE compound document).

The ComponentInfo stream is an 8-byte header (two uint16 markers, uint32 byte
length including a NUL terminator) followed by UTF-16-LE XML:
<Component_Root><Name>...</Name>... Bytes past that length are slack.
"""

from __future__ import annotations

import io
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import olefile


class ActionResourceError(ValueError):
    pass


@dataclass
class ActionResource:
    name: str
    description: str
    reusable: bool
    document_type: str


def read_action_resource(data: bytes) -> ActionResource:
    if not olefile.isOleFile(io.BytesIO(data)):
        raise ActionResourceError("Resource.mtr is not an OLE compound document.")
    with olefile.OleFileIO(io.BytesIO(data)) as ole:
        if not ole.exists("ComponentInfo"):
            raise ActionResourceError("Resource.mtr has no ComponentInfo stream.")
        stream = ole.openstream("ComponentInfo").read()
    if len(stream) < 8:
        raise ActionResourceError("ComponentInfo stream is truncated.")
    length = struct.unpack("<I", stream[4:8])[0]
    payload = stream[8:8 + length]
    if len(payload) != length:
        raise ActionResourceError("ComponentInfo stream is truncated.")
    try:
        root = ET.fromstring(payload.decode("utf-16-le").rstrip("\x00"))
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise ActionResourceError(f"ComponentInfo XML is unreadable: {exc}") from None
    name = (root.findtext("Name") or "").strip()
    if not name:
        raise ActionResourceError("ComponentInfo has no action name.")
    return ActionResource(
        name=name,
        description=root.findtext("Description") or "",
        reusable=(root.findtext("IsReusable") or "").strip() == "1",
        document_type=(root.findtext("DocumentType") or "").strip(),
    )
