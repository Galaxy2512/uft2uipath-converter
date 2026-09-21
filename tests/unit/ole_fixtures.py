"""Minimal CFB (OLE2) writer for test fixtures: one stream, >= 4096 bytes.

Streams at or above the mini-stream cutoff live in regular sectors, so no
mini FAT is needed. Layout: sector 0 = FAT, sector 1 = directory, then data.
"""
import struct

SECTOR = 512
FREE, END, FATSECT, NOSTREAM = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF


def _entry(name, kind, child=NOSTREAM, start=END, size=0):
    raw = name.encode("utf-16-le") + b"\x00\x00" if name else b""
    return (raw.ljust(64, b"\x00") + struct.pack("<HBB", len(raw), kind, 1 if kind else 0)
            + struct.pack("<III", NOSTREAM, NOSTREAM, child) + b"\x00" * 36
            + struct.pack("<IQ", start, size))


def ole_file(stream_name: str, data: bytes) -> bytes:
    data = data.ljust(4096, b"\x00")
    count = -(-len(data) // SECTOR)
    fat = [FATSECT, END] + [i + 3 for i in range(count - 1)] + [END]
    fat += [FREE] * (SECTOR // 4 - len(fat))
    header = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16
              + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\x00" * 6
              + struct.pack("<IIIIIIIII", 0, 1, 1, 0, 4096, END, 0, END, 0)
              + struct.pack("<I", 0) + struct.pack("<I", FREE) * 108)
    directory = (_entry("Root Entry", 5, child=1) + _entry(stream_name, 2, start=2, size=len(data))
                 + _entry("", 0) + _entry("", 0))
    return header + struct.pack("<128I", *fat) + directory + data.ljust(count * SECTOR, b"\x00")


def action_resource(name: str, reusable=True, shared_repositories=()) -> bytes:
    sors = "".join(f"<SOR ORDER_ID=\"{index}\"><![CDATA[{reference}]]></SOR>"
                   for index, reference in enumerate(shared_repositories))
    xml = ('<?xml version="1.0"?><Component_Root><Name><![CDATA[' + name + ']]></Name>'
           '<Description><![CDATA[]]></Description><DocumentType><![CDATA[Action]]></DocumentType>'
           f'<IsReusable><![CDATA[{int(reusable)}]]></IsReusable><SORs>{sors}</SORs></Component_Root>')
    payload = (xml + "\x00").encode("utf-16-le")
    return ole_file("ComponentInfo", struct.pack("<HHI", 2, 2, len(payload)) + payload + b"slack")
