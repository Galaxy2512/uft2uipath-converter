"""The types a migrated value can have, in one place.

UFT/VBScript is untyped: the converter gives every expression it migrates a
static type, because a UiPath variable, argument and C# expression all need
one. The mapping layer records the type of an argument, the generation layer
emits variables and arguments in it, so both must use the same names.

    String Boolean Int32 Double DateTime Object

Object is only used inside a workflow, to hold an activity result that has no
narrower type; arguments stay in ARGUMENT_TYPES so a caller sees a real type.
"""

STRING = "String"
BOOLEAN = "Boolean"
INT32 = "Int32"
DOUBLE = "Double"
DATE_TIME = "DateTime"
OBJECT = "Object"

#: Value type -> the type name written in XAML (s: and x: are Studio's prefixes).
XAML_TYPES = {
    STRING: "x:String", BOOLEAN: "x:Boolean", INT32: "x:Int32",
    DOUBLE: "x:Double", DATE_TIME: "s:DateTime", OBJECT: "x:Object",
}
#: Every value type an expression may have.
VALUE_TYPES = tuple(XAML_TYPES)
#: Types a workflow argument may have; the rest live only inside a workflow.
ARGUMENT_TYPES = (STRING, BOOLEAN, INT32)


def xaml_type(kind: str) -> str:
    """XAML type name of a value type, e.g. String -> x:String."""
    try:
        return XAML_TYPES[kind]
    except KeyError:
        raise ValueError(f"Unknown value type {kind!r}; expected one of {', '.join(VALUE_TYPES)}.") from None
