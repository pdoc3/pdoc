"""
This module exports the following classes:

* `DecoratedClassParent`
* `DecoratedClassChild`
"""

from .util import decorate_class
from abc import ABC, abstractmethod


@decorate_class
class DecoratedClassParent(ABC):
    """ This is `DecoratedClassParent` class. """

    @abstractmethod
    def __value__(self) -> int:
        """ An `DecoratedClassParent`'s value implementation, abstract method. """
        raise NotImplementedError

    @property
    def value(self) -> int:
        """ This is `DecoratedClassParent`'s property. """
        return self.__value__()


@decorate_class
class DecoratedClassChild(DecoratedClassParent):
    """ This is an `DecoratedClassParent`'s implementation that always returns 1. """

    def __value__(self) -> int:
        return 1


__all__ = [
    'DecoratedClassParent',
    'DecoratedClassChild',
]
