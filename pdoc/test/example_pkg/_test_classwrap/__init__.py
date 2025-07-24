"""
This is the root module.

This re-exports `DecoratedClassParent` and `DecoratedClassChild`.
See `pdoc.test.example_pkg._test_classwrap.class_definition.DecoratedClassParent`
and `pdoc.test.example_pkg._test_classwrap.class_definition.DecoratedClassChild` for more details.
"""


from .class_definition import DecoratedClassParent, DecoratedClassChild


__all__ = [
    'DecoratedClassParent',
    'DecoratedClassChild',
]
