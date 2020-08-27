from __future__ import annotations


class Foo:
    bar: "baz"    # noqa: F821 # ForwardRef not available, but also not really required
    dt: datetime  # noqa: F821
