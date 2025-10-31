import functools
import types
from typing import Type, TypeVar, cast


C = TypeVar('C')


def wrap_first(cls: Type[C]) -> Type[C]:
    wrapped = types.new_class(cls.__name__, (cls, ), {})
    wrapped = functools.update_wrapper(wrapped, cls, updated=())
    wrapped = cast(Type[C], wrapped)

    return wrapped


def wrap_second(cls: Type[C]) -> Type[C]:
    wrapped = type(cls.__name__, cls.__mro__, dict(cls.__dict__))
    wrapped = functools.update_wrapper(wrapped, cls, updated=())
    wrapped = cast(Type[C], wrapped)

    return wrapped


def decorate_class(cls: Type[C]) -> Type[C]:
    """ Creates a two-step class decoration. """

    wrapped = wrap_first(cls)
    wrapped_again = wrap_second(wrapped)
    wrapped_again.__decorated__ = True

    return wrapped_again


__all__ = [
    'decorate_class',
]
