"""Module docstring"""
from collections import namedtuple
import subprocess
import os

CONST = 'const'
"""CONST docstring"""

var = 2
"""var docstring"""

# https://github.com/mitmproxy/pdoc/pull/44
foreign_var = subprocess.CalledProcessError(0, '')
"""foreign var docstring"""

__pdoc__ = {}


def foo(env=os.environ):
    """Doesn't leak environ"""


def object_as_arg_default(*args, a=object(), **kwargs):
    """Html-encodes angle brackets in params"""


def _private_function():
    """Private function, should only appear if whitelisted"""


class A:
    """`A` is base class for `example_pkg.B`."""  # Test refname link
    def overridden(self):
        """A.overridden docstring"""

    def overridden_same_docstring(self):
        """A.overridden_same_docstring docstring"""

    def inherited(self):  # Inherited in B
        """A.inherited docstring"""

    def __call__(self):
        """A.__call__ docstring. Only shown when whitelisted"""


non_callable_routine = staticmethod(lambda x: 2)  # Not interpreted as Function; skipped


class ReadOnlyValueDescriptor:
    """Read-only value descriptor"""

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance.var ** 2
        return self


class B(A, int):
    """
    B docstring

    External refs: `sys.version`, `sys`
    """

    CONST = 2
    """B.CONST docstring"""

    var = 3
    """B.var docstring"""

    ro_value_descriptor = ReadOnlyValueDescriptor()
    """ro_value_descriptor docstring"""

    ro_value_descriptor_no_doc = ReadOnlyValueDescriptor()   # no doc-string

    def __init__(self, x, y, z, w):
        """`__init__` docstring"""
        self.instance_var = None
        """instance var docstring"""

        self._private_instance_var = None
        """This should be private (hidden) despite PEP 224 docstring"""

    def f(self, a: int, b: int = 1, *args, c: str = 'c', **kwargs):
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


class C(B): pass  # noqa: E701, E302
class D(C): pass  # noqa: E701, E302


class Hidden:
    __pdoc__['Hidden'] = False


class Docformats:
    def numpy(self):
        """
        Summary line.

        **Documentation**: https://pdoc3.github.io/pdoc/doc/pdoc/
        **Source Code**: https://github.com/pdoc3/

        Parameters
        ----------
        x1, x2 : array_like
            Input arrays,
            description of `x1`, `x2`.

            .. versionadded:: 1.5.0
        x : { NoneType, 'B', 'C' }, optional
        n : int or list of int
            Description of num
        *args, **kwargs
            Passed on.
        complex : Union[Set[pdoc.Doc, Function], pdoc]
            The `List[Doc]`s of the new signal.

        Returns
        -------
        output : pdoc.Doc
            The output array
        List[pdoc.Doc]
            The output array
        foo

        Raises
        ------
        TypeError
            When something.

        Raises
        ------
        TypeError

        Returns
        -------
        None.

        Invalid
        -------
        no match

        See Also
        --------
        fromstring, loadtxt

        See Also
        --------
        pdoc.text : Function a with its description.
        scipy.random.norm : Random variates, PDFs, etc.
        pdoc.Doc : A class description that
                   spans several lines.

        Examples
        --------
        >>> doctest
        ...

        Notes
        -----
        Foo bar.

        ### H3 Title

        Foo bar.
        """

    def google(self):
        """
        Summary line.
        Nomatch:

        Args:
            arg1 (str, optional): Text1
            arg2 (List[str], optional, default=10): Text2
            data (array-like object): foo

        Args:
          arg1 (int): Description of arg1
          arg2 (str or int): Description of arg2
          test_sequence: 2-dim numpy array of real numbers, size: N * D
            - the test observation sequence.

                test_sequence =
                code

            Continue.
          *args: passed around

        Returns:
            issue_10: description didn't work across multiple lines
                if only a single item was listed. `inspect.cleandoc()`
                somehow stripped the required extra indentation.

        Returns:
            A very special number
            which is the answer of everything.

        Returns:
            Dict[int, pdoc.Doc]: Description.

        Raises:
            AttributeError: The ``Raises`` section is a list of all exceptions
                that are relevant to the interface.

                and a third line.
            ValueError: If `arg2` is equal to `arg1`.

        Test a title without a blank line before it.
        Args:
            A: a

        Examples:
          Examples in doctest format.

          >>> a = [1,2,3]

        Todos:
            * For module TODOs
        """

    def doctests(self):
        """
        Need an intro paragrapgh.

            >>> Then code is indented one level
            line1
            line2

        Alternatively
        ```
        >>> doctest
        fenced code works
        always
        ```

        Examples:
            >>> nbytes(100)
            '100.0 bytes'
            line2

            some text

        some text

        >>> another doctest
        line1
        line2

        Example:
            >>> f()
            Traceback (most recent call last):
                ...
            Exception: something went wrong
        """

    def reST(self):
        """
        Summary line.

        Some stuff to test like http://www.python.org or `link_text <http://www.python.org>`_.
        Also *italic* and **bold**. And lists:

        * 1
        * 2

        #. Item
        #. Item

        :param arg1: Text1
        :parameter arg2: Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed
            diam nonumy eirmod tempor invidunt
        :arg arg_arg_3: Y:=H^T*X!@#$%^&&*()_[]{}';'::{[( :param just_in_case:
        :key str another_parameter:
        :type arg1: int
        :type arg2: Optional[List[Tuple[str]]]
        :type arg_arg_3: Dict[int, Dict[str, Any]]
        :var x: Description of variable x
        :ivar y: Description of variable y
        :cvar str z:
            Descriptions can also be placed in a new line.

            And span multiple lines.
        :vartype y: List[bool]
        :return: True. Or False. Depends
        :rtype: bool
        :meta: This should not be displayed in the generated output document

        A paragraph to split the field list into two.

        :returns: Now with more "s"
        :raise Exception: Raised occasionally
        :raises ZeroDivisionError: You know why and when

        Some more tests below:

        :rtype: int
        :vartype x: int
        :type z: str

        And now for some other stuff

        .. admonition:: TODO

           Create something.

        .. admonition:: Example

           Image shows something.

           .. image:: https://www.debian.org/logos/openlogo-nd-100.png

           .. note::
              Can only nest admonitions two levels.

        .. image:: https://www.debian.org/logos/openlogo-nd-100.png

        Now you know.

        .. warning::

            Some warning
            lines.

        * Describe some func in a list
          across multiple lines:

            .. admonition:: Deprecated since 3.1

                Use `spam` instead.

            .. admonition:: Added in version 2.5

                The *spam* parameter.

        .. caution::
            Don't touch this!
        """

    def reST_directives(self):
        """
        .. todo::

           Create something.

        .. admonition:: Example

           Image shows something.

           .. image:: https://www.debian.org/logos/openlogo-nd-100.png

           .. note::
              Can only nest admonitions two levels.

        .. image:: https://www.debian.org/logos/openlogo-nd-100.png

        Now you know.

        .. warning::

            Some warning
            lines.

        * Describe some func in a list
          across multiple lines:

            .. deprecated:: 3.1
              Use `spam` instead.

            .. versionadded:: 2.5
             The *spam* parameter.

        .. caution::
            Don't touch this!
        """


numpy = Docformats.numpy


google = Docformats.google


doctests = Docformats.doctests


reST = Docformats.reST


reST_directives = Docformats.reST_directives


def latex_math():
    """
    Inline equation: \\( v_t *\\frac{1}{2}* j_i + [a] < 3 \\).

    Block equation: \\[ v_t *\\frac{1}{2}* j_i + [a] < 3 \\]

    Block equation: $$ v_t *\\frac{1}{2}* j_i + [a] < 3 $$

    ..math::
        v_t *\\frac{1}{2}* j_i + [a] < 3
    """


class Location(namedtuple('Location', 'lat lon')):
    """Geo-location, GPS position."""
