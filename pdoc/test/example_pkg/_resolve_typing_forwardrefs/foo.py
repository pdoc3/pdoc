from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime


class Foo:
    bar: "baz"  # noqa: F821  # ForwardRef not available, but also not really required
    dt: datetime
