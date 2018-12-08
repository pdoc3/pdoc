"""Module docstring"""
import subprocess

CONST = 'const'
"""CONST docstring"""

var = 2
"""var docstring"""

# https://github.com/mitmproxy/pdoc/pull/44
foreign_var = subprocess.CalledProcessError(0, '')
"""foreign var docstring"""

__pdoc__ = {}


class A:
    """`A` is base class for `example_pkg.B`."""  # Test refname link
    def overridden(self):
        """A.overridden docstring"""

    def overridden_same_docstring(self):
        """A.overridden_same_docstring docstring"""

    def inherited(self):  # Inherited in B
        """A.inherited docstring"""


class B(A, int):
    """
    B docstring

    External: `sys.version`, `sys`
    """

    CONST = 2
    """B.CONST docstring"""

    var = 3
    """B.var docstring"""

    def __init__(self):
        """__init__ docstring"""
        self.instance_var = None
        """instance var docstring"""

    def f(self, a: int, b: int = 1, *args, c: str='c', **kwargs):
        """B.f docstring"""

    @staticmethod
    def static(x):
        """B.static docstring"""

    @classmethod
    def cls(cls):
        """B.cls docstring"""

    def _private(self):
        """B._private docstring"""

    @staticmethod
    def _private_static():
        """B._private_static docstring"""

    @classmethod
    def _private_cls(cls):
        """B._private_cls docstring"""

    @property
    def p(self):
        """B.p docstring"""
        return 1

    class C:
        """B.C docstring"""
        def f(self):
            """B.C.f docstring"""

    class _Private:
        """B._Private docstring"""
        def f(self):
            """B._Private.f docstring"""

    def overridden(self):
        pass

    assert overridden.__doc__ is None
    __pdoc__['B.overridden'] = 'B.overridden docstring'

    def overridden_same_docstring(self):
        pass


class Hidden:
    __pdoc__['Hidden'] = False
