"""Read the public shape of UiPath activity types from the installed packages.

The converter may not guess what a UiPath activity looks like. Studio clipboard
samples are the first source (docs/activity_lab); this is the second: the
vendor's own assemblies in the local NuGet cache, which name every property of
every activity and its type.

    python tools/read_activity_metadata.py NClick NTypeInto NApplicationCard

Prints each type with its properties and their .NET types, so a modern activity
can be emitted with the right property names instead of invented ones. What a
property means, and whether Studio writes it at all, still has to be confirmed
against a Studio sample.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import dnfile
from dnfile.mdtable import MethodSemanticsRow

NUGET = Path.home() / ".nuget" / "packages"
# The assemblies that hold the modern (Next) and classic UI activities.
PACKAGES = ("uipath.uiautomation.activities.runtime", "uipath.uiautomation.activities")


def _version_key(name: str) -> tuple:
    """Sort 26.10.1 above 9.9.9 and keep non-numeric parts last."""
    return tuple(int(part) if part.isdigit() else -1 for part in re.split(r"[.\-]", name))


def assemblies(packages=PACKAGES) -> list[Path]:
    """Every .dll of the newest installed version of each package."""
    found: list[Path] = []
    for package in packages:
        root = NUGET / package
        if not root.is_dir():
            continue
        newest = max((path for path in root.iterdir() if path.is_dir()), key=lambda p: _version_key(p.name))
        found.extend(sorted(newest.rglob("*.dll")))
    return found


def types_of(path: Path) -> dict[str, dict]:
    """Type name -> {"base": name, "properties": [(property, type)]} for one assembly."""
    try:
        pe = dnfile.dnPE(str(path), fast_load=False)
    except Exception:  # noqa: BLE001 - a native dll is simply not managed
        return {}
    tables = pe.net.mdtables if pe.net else None
    maps = getattr(tables, "PropertyMap", None) if tables else None
    if maps is None:
        return {}
    # Each PropertyMap row names a type and the properties declared on it;
    # everything else the activity has, it inherits from its base type.
    result: dict[str, dict] = {}
    for row in maps.rows:
        owner = row.Parent.row
        if owner is None:
            continue
        # Extends points at a TypeDef, a TypeRef or a TypeSpec; only the first
        # two name a type this assembly can tell us anything about.
        base = getattr(getattr(owner, "Extends", None), "row", None)
        base_name = getattr(base, "TypeName", None)
        result[str(owner.TypeName)] = {
            "base": str(base_name) if base_name is not None else None,
            "properties": [(str(ref.row.Name), _signature(tables, ref.row))
                           for ref in row.PropertyList if ref.row is not None],
        }
    return result


def enums_of(path: Path) -> dict[str, list[str]]:
    """Enum name -> its member names, for every enum in one assembly.

    A property of an enum type is written in XAML as one of these names, so a
    generated activity can use the right word instead of a plausible one.
    """
    try:
        pe = dnfile.dnPE(str(path), fast_load=False)
    except Exception:  # noqa: BLE001 - a native dll is simply not managed
        return {}
    tables = pe.net.mdtables if pe.net else None
    if tables is None or not getattr(tables, "TypeDef", None):
        return {}
    found: dict[str, list[str]] = {}
    for row in tables.TypeDef.rows:
        base = getattr(getattr(row, "Extends", None), "row", None)
        if str(getattr(base, "TypeName", "")) != "Enum":
            continue
        # The first field carries the underlying value; the rest are the members.
        members = [str(ref.row.Name) for ref in row.FieldList
                   if ref.row is not None and str(ref.row.Name) != "value__"]
        if members:
            found[str(row.TypeName)] = members
    return found


def with_inherited(found: dict[str, dict], name: str) -> list[tuple[str, str, str]]:
    """Properties of a type and of every base type, as (property, type, declared on)."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    while name and name in found and name not in seen:
        seen.add(name)
        out += [(prop, kind, name) for prop, kind in found[name]["properties"]]
        name = found[name]["base"]
    return out


# ECMA-335 II.23.1.16: the element types a property signature can use.
PRIMITIVES = {
    0x01: "Void", 0x02: "Boolean", 0x03: "Char", 0x04: "SByte", 0x05: "Byte", 0x06: "Int16",
    0x07: "UInt16", 0x08: "Int32", 0x09: "UInt32", 0x0A: "Int64", 0x0B: "UInt64", 0x0C: "Single",
    0x0D: "Double", 0x0E: "String", 0x18: "IntPtr", 0x19: "UIntPtr", 0x1C: "Object",
}


def _compressed(data: bytes, at: int) -> tuple[int, int]:
    """Read one compressed unsigned integer (II.23.2); returns the value and the next position."""
    first = data[at]
    if first < 0x80:
        return first, at + 1
    if first < 0xC0:
        return ((first & 0x3F) << 8) | data[at + 1], at + 2
    return (((first & 0x1F) << 24) | (data[at + 1] << 16) | (data[at + 2] << 8) | data[at + 3]), at + 4


def _type_name(tables, token: int) -> str:
    """Name behind a TypeDefOrRef coded index (II.23.2.8)."""
    table = {0: "TypeDef", 1: "TypeRef", 2: "TypeSpec"}.get(token & 0x3, "TypeSpec")
    index = (token >> 2) - 1
    rows = getattr(getattr(tables, table, None), "rows", [])
    if table == "TypeSpec" or not 0 <= index < len(rows):
        return table
    return str(rows[index].TypeName)


def _read_type(tables, data: bytes, at: int) -> tuple[str, int]:
    """One type in a signature blob, as a readable name."""
    code = data[at]
    at += 1
    if code in PRIMITIVES:
        return PRIMITIVES[code], at
    if code in (0x11, 0x12):  # VALUETYPE, CLASS
        token, at = _compressed(data, at)
        return _type_name(tables, token), at
    if code == 0x15:  # GENERICINST
        outer, at = _read_type(tables, data, at)
        count, at = _compressed(data, at)
        args = []
        for _ in range(count):
            name, at = _read_type(tables, data, at)
            args.append(name)
        return f"{outer.split('`')[0]}<{', '.join(args)}>", at
    if code == 0x1D:  # SZARRAY
        inner, at = _read_type(tables, data, at)
        return f"{inner}[]", at
    if code in (0x1F, 0x20):  # CMOD_REQD, CMOD_OPT
        _, at = _compressed(data, at)
        return _read_type(tables, data, at)
    return f"code_{code:#x}", at


def _signature(tables, row) -> str:
    """Type of a property, decoded from its signature blob."""
    blob = getattr(row, "Type", None)
    data = bytes(getattr(blob, "value", b"") or b"")
    if len(data) < 3:
        return "?"
    try:
        # PROPERTY (0x08, plus HASTHIS 0x20), parameter count, then the type.
        _, at = _compressed(data, 1)
        return _read_type(tables, data, at)[0]
    except (IndexError, ValueError):
        return "?"


def main(argv=None):
    """Print the properties of the named types, or list every activity type."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("types", nargs="*", help="type names, e.g. NClick (default: list activities)")
    parser.add_argument("--contains", help="only types whose name contains this")
    parser.add_argument("--enums", action="store_true", help="print the members of the named enums")
    args = parser.parse_args(argv)

    wanted = {name.casefold() for name in args.types}
    if args.enums:
        for path in assemblies():
            for name, members in sorted(enums_of(path).items()):
                if (wanted and name.casefold() in wanted) or (
                        args.contains and args.contains.casefold() in name.casefold()):
                    print(f"\n== {name}  ({path.name})\n   " + ", ".join(members))
        return
    for path in assemblies():
        found = types_of(path)
        if not found:
            continue
        for name in sorted(found):
            if wanted and name.casefold() not in wanted:
                continue
            if args.contains and args.contains.casefold() not in name.casefold():
                continue
            if not wanted and not args.contains:
                continue
            print(f"\n== {name}  ({path.name})")
            for prop, kind, declared in sorted(with_inherited(found, name)):
                inherited = "" if declared == name else f"  (from {declared})"
                print(f"   {prop:<28} {kind}{inherited}")


if __name__ == "__main__":
    main()
