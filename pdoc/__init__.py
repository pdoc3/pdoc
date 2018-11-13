"""
Module pdoc provides types and functions for accessing the public
documentation of a Python module. This includes modules (and
sub-modules), functions, classes and module, class and instance
variables.  Docstrings are taken from modules, functions and classes
using the special `__doc__` attribute. Docstrings for variables are
extracted by examining the module's abstract syntax tree.

The public interface of a module is determined through one of two
ways. If `__all__` is defined in the module, then all identifiers in
that list will be considered public. No other identifiers will be
considered as public. Conversely, if `__all__` is not defined, then
`pdoc` will heuristically determine the public interface. There are
three rules that are applied to each identifier in the module:

1. If the name starts with an underscore, it is **not** public.

2. If the name is defined in a different module, it is **not** public.

3. If the name refers to an immediate sub-module, then it is public.

Once documentation for a module is created with `pdoc.Module`, it
can be output as either HTML or plain text using the covenience
functions `pdoc.html` and `pdoc.text`, or the corresponding methods
`pdoc.Module.html` and `pdoc.Module.text`.

Alternatively, you may run an HTTP server with the `pdoc` script
included with this module.


Compatibility
-------------
`pdoc` has been tested on Python 2.6, 2.7 and 3.3. It seems to work
on all three.


Contributing
------------
`pdoc` [is on GitHub](https://github.com/BurntSushi/pdoc). Pull
requests and bug reports are welcome.


Linking to other identifiers
----------------------------
In your documentation, you may link to other identifiers in
your module or submodules. Linking is automatically done for
you whenever you surround an identifier with a back quote
(grave). The identifier name must be fully qualified. For
example, <code>\`pdoc.Doc.docstring\`</code> is correct while
<code>\`Doc.docstring\`</code> is incorrect.

If the `pdoc` script is used to run an HTTP server, then external
linking to other packages installed is possible. No extra work is
necessary; simply use the fully qualified path. For example,
<code>\`nflvid.slice\`</code> will create a link to the `nflvid.slice`
function, which is **not** a part of `pdoc` at all.


Where does pdoc get documentation from?
---------------------------------------
Broadly speaking, `pdoc` gets everything you see from introspecting the
module. This includes words describing a particular module, class,
function or variable. While `pdoc` does some analysis on the source
code of a module, importing the module itself is necessary to use
Python's introspection features.

In Python, objects like modules, functions, classes and methods have
a special attribute named `__doc__` which contains that object's
*docstring*.  The docstring comes from a special placement of a string
in your source code.  For example, the following code shows how to
define a function with a docstring and access the contents of that
docstring:

    #!python
    >>> def test():
    ...     '''This is a docstring.'''
    ...     pass
    ...
    >>> test.__doc__
    'This is a docstring.'

Something similar can be done for classes and modules too. For classes,
the docstring should come on the line immediately following `class
...`. For modules, the docstring should start on the first line of
the file. These docstrings are what you see for each module, class,
function and method listed in the documentation produced by `pdoc`.

The above just about covers *standard* uses of docstrings in Python.
`pdoc` extends the above in a few important ways.


### Special docstring conventions used by `pdoc`

**Firstly**, docstrings can be inherited. Consider the following code
sample:

    #!python
    >>> class A (object):
    ...     def test():
    ...         '''Docstring for A.'''
    ...
    >>> class B (A):
    ...     def test():
    ...         pass
    ...
    >>> print(A.test.__doc__)
    Docstring for A.
    >>> print(B.test.__doc__)
    None

In Python, the docstring for `B.test` is empty, even though one was
defined in `A.test`. If `pdoc` generates documentation for the above
code, then it will automatically attach the docstring for `A.test` to
`B.test` only if `B.test` does not have a docstring. In the default
HTML output, an inherited docstring is grey.

**Secondly**, docstrings can be attached to variables, which includes
module (or global) variables, class variables and instance variables.
Python by itself [does not allow docstrings to be attached to
variables](http://www.python.org/dev/peps/pep-0224). For example:

    #!python
    variable = "SomeValue"
    '''Docstring for variable.'''

The resulting `variable` will have no `__doc__` attribute. To
compensate, `pdoc` will read the source code when it's available to
infer a connection between a variable and a docstring. The connection
is only made when an assignment statement is followed by a docstring.

Something similar is done for instance variables as well. By
convention, instance variables are initialized in a class's `__init__`
method.  Therefore, `pdoc` adheres to that convention and looks for
docstrings of variables like so:

    #!python
    def __init__(self):
        self.variable = "SomeValue"
        '''Docstring for instance variable.'''

Note that `pdoc` only considers attributes defined on `self` as
instance variables.

Class and instance variables can also have inherited docstrings.

**Thirdly and finally**, docstrings can be overridden with a special
`__pdoc__` dictionary that `pdoc` inspects if it exists. The keys of
`__pdoc__` should be identifiers within the scope of the module. (In
the case of an instance variable `self.variable` for class `A`, its
module identifier would be `A.variable`.) The values of `__pdoc__`
should be docstrings.

This particular feature is useful when there's no feasible way of
attaching a docstring to something. A good example of this is a
[namedtuple](http://goo.gl/akfXJ9):

    #!python
    __pdoc__ = {}

    Table = namedtuple('Table', ['types', 'names', 'rows'])
    __pdoc__['Table.types'] = 'Types for each column in the table.'
    __pdoc__['Table.names'] = 'The names of each column in the table.'
    __pdoc__['Table.rows'] = 'Lists corresponding to each row in the table.'

`pdoc` will then show `Table` as a class with documentation for the
`types`, `names` and `rows` members.

Note that assignments to `__pdoc__` need to placed where they'll be
executed when the module is imported. For example, at the top level
of a module or in the definition of a class.

If `__pdoc__[key] = None`, then `key` will not be included in the
public interface of the module.


License
-------
`pdoc` is licensed under the terms of GNU [AGPL-3.0] or later.

[AGPL-3.0]: https://www.gnu.org/licenses/agpl-3.0.html
"""
import ast
import importlib.util
import inspect
import os
import os.path as path
import pkgutil
import re
import sys
from copy import copy
from itertools import chain, tee
from warnings import warn

from mako.lookup import TemplateLookup
from mako.exceptions import TopLevelLookupException


__version__ = "0.3.2"
"""
The current version of pdoc. This value is read from `setup.py`.
"""

_URL_MODULE_SUFFIX = '.html'
_URL_INDEX_MODULE_SUFFIX = '.m.html'  # For modules named literal 'index'
_URL_PACKAGE_SUFFIX = '/index.html'

__pdoc__ = {}

tpl_lookup = TemplateLookup(
    cache_args=dict(cached=True,
                    cache_type='memory'),
    input_encoding='utf-8',
    directories=[path.join(path.dirname(__file__), "templates")],
)
"""
A `mako.lookup.TemplateLookup` object that knows how to load templates
from the file system. You may add additional paths by modifying the
object's `directories` attribute.
"""
if os.getenv("XDG_CONFIG_HOME"):
    tpl_lookup.directories.insert(0, path.join(os.getenv("XDG_CONFIG_HOME"), "pdoc"))


def _render_template(template_name, **kwargs):
    """
    Returns the Mako template with the given name.  If the template
    cannot be found, a nicer error message is displayed.
    """
    try:
        t = tpl_lookup.get_template(template_name)
    except TopLevelLookupException:
        raise OSError(
            "No template found at any of: {}".format(
                ', '.join(path.join(p, template_name.lstrip("/"))
                          for p in tpl_lookup.directories)))
    try:
        return t.render(**kwargs).strip()
    except Exception:
        from mako import exceptions
        print(exceptions.text_error_template().render(),
              file=sys.stderr)
        raise


def html(
    module_name,
    docfilter=None,
    external_links=False,
    link_prefix="",
    source=True,
    **kwargs
) -> str:
    """
    Returns the documentation for the module `module_name` in HTML
    format. The module must be importable.

    `docfilter` is an optional predicate that controls which
    documentation objects are shown in the output. It is a single
    argument function that takes a documentation object and returns
    `True` or `False`. If `False`, that object will not be included in
    the output.

    If `external_links` is `True`, then identifiers to external modules
    are always turned into links.

    If `link_prefix` is `True`, then all links will have that prefix.
    Otherwise, links are always relative.

    If `source` is `True`, then source code will be retrieved for
    every Python object whenever possible. This can dramatically
    decrease performance when documenting large modules.
    """
    mod = Module(import_module(module_name), docfilter=docfilter)
    return mod.html(external_links=external_links,
                    link_prefix=link_prefix,
                    source=source,
                    **kwargs)


def text(module_name, docfilter=None, **kwargs) -> str:
    """
    Returns the documentation for the module `module_name` in plain
    text format. The module must be importable.

    `docfilter` is an optional predicate that controls which
    documentation objects are shown in the output. It is a single
    argument function that takes a documentation object and returns
    True of False. If False, that object will not be included in the
    output.
    """
    mod = Module(import_module(module_name), docfilter=docfilter)
    return mod.text(**kwargs)


def import_module(module: str):
    """
    Return module object matching `module` specification (either a python
    module path or a filesystem path to file/directory).
    """
    if isinstance(module, Module):
        module = module.module
    if isinstance(module, str):
        try:
            module = importlib.import_module(module)
        except ImportError:
            pass
        except Exception as e:
            raise ImportError('Error importing {!r}: {}'.format(module, e))

    if inspect.ismodule(module):
        if module.__name__.startswith(__name__):
            # If this is pdoc itself, return without reloading.
            # Otherwise most `isinstance(..., pdoc.Doc)` calls won't
            # work correctly.
            return module
        return importlib.reload(module)

    # Try to load it as a filename
    if path.exists(module) and module.endswith('.py'):
        filename = module
    elif path.exists(module + '.py'):
        filename = module + '.py'
    elif path.exists(path.join(module, '__init__.py')):
        filename = path.join(module, '__init__.py')
    else:
        raise ValueError('File or module {!r} not found'.format(module))

    # If the path is relative, the whole of it is a python module path.
    # If the path is absolute, only the basename is.
    module_name = path.splitext(module)[0]
    if path.isabs(module):
        module_name = path.basename(module_name)
    else:
        module_name = path.splitdrive(module_name)[1]
    module_name = module_name.replace(path.sep, '.')

    spec = importlib.util.spec_from_file_location(module_name, path.abspath(filename))
    module = importlib.util.module_from_spec(spec)
    try:
        module.__loader__.exec_module(module)
    except Exception as e:
        raise ImportError('Error importing {!r}: {}'.format(filename, e))

    # For some reason, `importlib.util.module_from_spec` doesn't add
    # the module into `sys.modules`, and this later fails when
    # `inspect.getsource` tries to retrieve the module in AST parsing
    try:
        if sys.modules[module_name].__file__ != module.__file__:
            warn("Module {!r} in sys.modules loaded from {!r}. "
                 "Now reloaded from {!r}.".format(module_name,
                                                  sys.modules[module_name].__file__,
                                                  module.__file__))
    except KeyError:  # Module not yet in sys.modules
        pass
    sys.modules[module_name] = module

    return module


def _pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def _var_docstrings(doc_obj: 'Doc', *, _init_tree: ast.AST = None) -> dict:
    """
    Extracts docstrings for variables of `doc_obj`
    (either a `pdoc.Module` or `pdoc.Class`).

    Returns a dict mapping variable names to `pdoc.Variable` objects.

    For `pdoc.Class` objects, the dict contains class' instance
    variables (defined as `self.something` in class' `__init__`),
    recognized by `Variable.instance_var == True`.
    """
    assert isinstance(doc_obj, (Module, Class))

    if _init_tree:
        tree = _init_tree
    else:
        try:
            tree = ast.parse(inspect.getsource(doc_obj.obj))
        except (OSError, TypeError, SyntaxError):
            warn("Couldn't get/parse source of '{!r}'".format(doc_obj))
            return {}
        if isinstance(doc_obj, Class):
            tree = tree.body[0]  # ast.parse creates a dummy ast.Module wrapper we don't need

    vs = {}

    cls = None
    module = doc_obj
    module_all = getattr(module.obj, '__all__', None)

    if isinstance(doc_obj, Class):
        cls = doc_obj
        module = doc_obj.module
        module_all = None  # If documenting a class, we needn't look into __all__

        # For classes, first add instance variables defined in __init__
        if not _init_tree:
            try:
                # Recursive call with just the __init__ tree
                vs = _var_docstrings(
                    doc_obj, _init_tree=next(
                        node for node in tree.body
                        if (isinstance(node, ast.FunctionDef) and
                            node.name == '__init__')))
            except StopIteration:
                pass

    if module_all is not None:
        module_all = set(module_all)

    try:
        ast_AnnAssign = ast.AnnAssign
    except AttributeError:  # Python < 3.6
        ast_AnnAssign = type(None)
    ast_Assignments = (ast.Assign, ast_AnnAssign)

    for assign_node, str_node in _pairwise(ast.iter_child_nodes(tree)):
        if not (isinstance(assign_node, ast_Assignments) and
                isinstance(str_node, ast.Expr) and
                isinstance(str_node.value, ast.Str)):
            continue

        if isinstance(assign_node, ast.Assign) and len(assign_node.targets) == 1:
            target = assign_node.targets[0]
        elif isinstance(assign_node, ast_AnnAssign):
            target = assign_node.target
            # TODO: use annotation
        else:
            continue

        if not _init_tree and isinstance(target, ast.Name):
            name = target.id
        elif (_init_tree and
              isinstance(target, ast.Attribute) and
              isinstance(target.value, ast.Name) and
              target.value.id == 'self'):
            name = target.attr
        else:
            continue

        if not _is_public(name):
            continue

        if module_all is not None and name not in module_all:
            continue

        docstring = inspect.cleandoc(str_node.value.s).strip()
        if not docstring:
            continue

        vs[name] = Variable(name, module, docstring,
                            cls=cls, instance_var=bool(_init_tree))
    return vs


def _is_public(ident_name):
    """
    Returns `True` if `ident_name` matches the export criteria for an
    identifier name.

    This should not be used by clients. Instead, use
    `pdoc.Module.is_public`.
    """
    return not ident_name.startswith("_")


class Doc:
    """
    A base class for all documentation objects.

    A documentation object corresponds to *something* in a Python module
    that has a docstring associated with it. Typically, this only includes
    modules, classes, functions and methods. However, `pdoc` adds support
    for extracting docstrings from the abstract syntax tree, which means
    that variables (module, class or instance) are supported too.

    A special type of documentation object `pdoc.External` is used to
    represent identifiers that are not part of the public interface of
    a module. (The name "External" is a bit of a misnomer, since it can
    also correspond to unexported members of the module, particularly in
    a class's ancestor list.)
    """

    def __init__(self, name, module, obj, docstring=None):
        """
        Initializes a documentation object, where `name` is the public
        identifier name, `module` is a `pdoc.Module` object, and
        `docstring` is a string containing the docstring for `name`.
        """
        self.module = module
        """
        The module documentation object that this object is defined in.
        """

        self.name = name
        """
        The identifier name for this object.
        """

        self.obj = obj
        """
        The raw python object.
        """

        self.docstring = (docstring or inspect.getdoc(obj) or '').strip()
        """
        The cleaned docstring for this object.
        """

        self.inherits = None  # type: Union[Class, Function, Variable]
        """
        The Doc object (Class, Function, or Variable) this object inherits from,
        if any.
        """

    def __repr__(self):
        return '<{} {!r}>'.format(self.__class__.__name__, self.refname)

    @property
    def source(self):
        """
        Cleaned (dedented) source code of the Python object. If not
        available, an empty string.
        """
        try:
            lines, _ = inspect.getsourcelines(self.obj)
        except (ValueError, TypeError, OSError):
            return ''
        return inspect.cleandoc(''.join(['\n'] + lines))

    @property
    def refname(self):
        """
        Reference name of this documentation
        object, usually its fully qualified path
        (e.g. <code>pdoc.Doc.refname</code>). Every
        documentation object provides this property.
        """
        # Ok for Module and External, the rest need it overriden
        return self.name

    @property
    def qualname(self):
        """
        Module-relative "qualified" name of this documentation
        object, used for show (e.g. <code>Doc.qualname</code>).
        """
        return getattr(self.obj, '__qualname__', self.name)

    def url(self, relative_to: 'Module' = None, *, link_prefix: str = ''):
        """
        Canonical relative URL (including page fragment) for this
        documentation object.
        """
        if relative_to is None or link_prefix:
            return link_prefix + self._url()

        if self.module.name == relative_to.name:
            return '#' + self.refname

        # Otherwise, compute relative path from current module to link target
        url = os.path.relpath(self._url(), relative_to.url())
        # We have one set of '..' too many
        if url.startswith('../'):
            url = url[3:]
        return url

    def _url(self):
        return self.module._url() + '#' + self.refname

    def inherits_top(self):
        """
        Follow the `pdoc.Doc.inherits` chain and return the top object.
        """
        top = self
        while top.inherits:
            top = top.inherits
        return top

    def __lt__(self, other):
        return self.name < other.name


class Module(Doc):
    """
    Representation of a module's documentation.
    """

    __pdoc__["Module.module"] = "The Python module object."
    __pdoc__[
        "Module.name"
    ] = """
        The name of this module with respect to the context in which
        it was imported. It is always an absolute import path.
        """

    def __init__(self, module, docfilter=None, supermodule=None):
        """
        Creates a `Module` documentation object given the actual
        module Python object.

        `docfilter` is an optional predicate that controls which
        documentation objects are returned in the following
        methods: `pdoc.Module.classes`, `pdoc.Module.functions`,
        `pdoc.Module.variables` and `pdoc.Module.submodules`. The
        filter is propagated to the analogous methods on a `pdoc.Class`
        object.
        """
        super().__init__(module.__name__, self, module)

        self._docfilter = docfilter or (lambda _: True)
        self.supermodule = supermodule
        self._submodules = []

        self.doc = {}
        """A mapping from identifier name to a documentation object."""

        self.refdoc = {}
        """
        The same as `pdoc.Module.doc`, but maps fully qualified
        identifier names to documentation objects.
        """

        # Populate self.doc with this module's public members
        if hasattr(self.obj, '__all__'):
            module_all = set(self.obj.__all__)
            public_objs = [(name, inspect.unwrap(obj))
                           for name, obj in inspect.getmembers(self.obj)
                           if name in module_all]
        else:
            def is_from_this_module(obj):
                mod = inspect.getmodule(obj)
                return mod is None or mod.__name__ in self.obj.__name__

            public_objs = [(name, inspect.unwrap(obj))
                           for name, obj in inspect.getmembers(self.obj)
                           if (_is_public(name) and
                               is_from_this_module(obj))]

        for name, obj in public_objs:
            if inspect.isroutine(obj):
                self.doc[name] = Function(name, self, obj)
            elif inspect.isclass(obj):
                self.doc[name] = Class(name, self, obj)

        self.doc.update(_var_docstrings(self))

        # If the module is a package, scan the directory for submodules
        if self.is_package:
            loc = getattr(self.module, "__path__", [path.dirname(self.obj.__file__)])
            for _, root, _ in pkgutil.iter_modules(loc):
                # Ignore if this module was already doc'd.
                if root in self.doc:
                    continue

                # Ignore if it isn't exported
                if not _is_public(root):
                    continue

                assert self.refname == self.name
                fullname = "%s.%s" % (self.name, root)
                m = import_module(fullname)

                submodule = Module(m, docfilter=self._docfilter, supermodule=self)
                self._submodules.append(submodule)
                self.doc[root] = submodule
            self._submodules.sort()

        # Build the reference name dictionary of the module
        for docobj in self.doc.values():
            self.refdoc[docobj.refname] = docobj
            if isinstance(docobj, Class):
                self.refdoc.update((obj.refname, obj)
                                   for obj in chain(docobj.class_variables(),
                                                    docobj.instance_variables(),
                                                    docobj.methods(),
                                                    docobj.functions()))

        # Finally look for more docstrings in the __pdoc__ override.
        for name, docstring in getattr(self.obj, "__pdoc__", {}).items():
            refname = "%s.%s" % (self.refname, name)
            if docstring is None:
                self.doc.pop(name, None)
                self.refdoc.pop(refname, None)
                continue

            dobj = self.find_ident(refname)
            if isinstance(dobj, External):
                continue
            assert isinstance(docstring, str), (type(docstring), docstring)
            dobj.docstring = inspect.cleandoc(docstring)

        # Now that we have all refnames, link inheritance relationships
        # between classes and their members
        for docobj in self.doc.values():
            if isinstance(docobj, Class):
                docobj._fill_inheritance()

    def text(self, **kwargs):
        """
        Returns the documentation for this module as plain text.
        """
        txt = _render_template('/text.mako', module=self, **kwargs)
        return re.sub("\n\n\n+", "\n\n", txt)

    def html(self, external_links=False, link_prefix="", source=True, minify=True, **kwargs):
        """
        Returns the documentation for this module as
        self-contained HTML.

        If `external_links` is `True`, then identifiers to external
        modules are always turned into links.

        If `link_prefix` is `True`, then all links will have that
        prefix. Otherwise, links are always relative.

        If `source` is `True`, then source code will be retrieved for
        every Python object whenever possible. This can dramatically
        decrease performance when documenting large modules.

        If `minify` is `True`, the resulting HTML is minified.

        `kwargs` is passed to the `mako` render function.
        """
        html = _render_template('/html.mako',
                                module=self,
                                external_links=external_links,
                                link_prefix=link_prefix,
                                show_source_code=source,
                                **kwargs)
        if minify:
            from pdoc.html_helpers import minify_html
            html = minify_html(html)
        return html

    @property
    def is_package(self):
        """
        `True` if this module is a package.

        Works by checking whether the module has a `__path__` attribute.
        """
        return hasattr(self.obj, "__path__")

    def find_class(self, cls: type):
        """
        Given a Python `cls` object, try to find it in this module
        or in any of the exported identifiers of the submodules.
        """
        # XXX: Is this corrent? Does it always match
        # `Class.module.name + Class.qualname`?.
        # If not, see what was here before.
        return self.find_ident(cls.__module__ + '.' + cls.__qualname__)

    def find_ident(self, name: str):
        """
        Searches this module and **all** of its public sub/super-modules
        for an identifier with name `name` in its list of exported
        identifiers according to `pdoc`.

        A bare identifier (without `.` separators) will only be checked
        for in this module.

        The documentation object corresponding to the identifier is
        returned. If one cannot be found, then an instance of
        `External` is returned populated with the given identifier.
        """
        # Without dot only look in the current module
        if '.' not in name:
            return self.doc.get(name) or External(name)

        for module in chain((self,),
                            self._submodules_recursive(),
                            self._supermodules_recursive()):
            if name == module.refname:
                return module
            if name in module.refdoc:
                return module.refdoc[name]

        return External(name)

    def _submodules_recursive(self):
        yield from self._submodules
        for module in self._submodules:
            yield from module._submodules_recursive()

    def _supermodules_recursive(self):
        module = self.supermodule
        while module is not None:
            yield module
            module = module.supermodule

    def _filter_doc_objs(self, type: type = Doc):
        return sorted(obj for obj in self.doc.values()
                      if isinstance(obj, type) and self._docfilter(obj))

    def variables(self):
        """
        Returns all documented module level variables in the module
        sorted alphabetically as a list of `pdoc.Variable`.
        """
        return self._filter_doc_objs(Variable)

    def classes(self):
        """
        Returns all documented module level classes in the module
        sorted alphabetically as a list of `pdoc.Class`.
        """
        return self._filter_doc_objs(Class)

    def functions(self):
        """
        Returns all documented module level functions in the module
        sorted alphabetically as a list of `pdoc.Function`.
        """
        return self._filter_doc_objs(Function)

    def submodules(self):
        """
        Returns all documented sub-modules in the module sorted
        alphabetically as a list of `pdoc.Module`.
        """
        return [m for m in self._submodules if self._docfilter(m)]

    def _url(self):
        url = self.module.name.replace('.', '/')
        if self.is_package:
            return url + _URL_PACKAGE_SUFFIX
        elif url.endswith('/index'):
            return url + _URL_INDEX_MODULE_SUFFIX
        return url + _URL_MODULE_SUFFIX


class Class(Doc):
    """
    Representation of a class's documentation.
    """

    def __init__(self, name, module, class_obj):
        """
        Same as `pdoc.Doc.__init__`, except `class_obj` must be a
        Python class object. The docstring is gathered automatically.
        """
        super().__init__(name, module, class_obj)

        self.doc = {}
        """A mapping from identifier name to a `pdoc.Doc` objects."""

        self.doc.update(_var_docstrings(self))

        def forced_out(name, _pdoc_overrides=getattr(self.module.obj, '__pdoc__', {}).get):
            return _pdoc_overrides(self.name + '.' + name, False) is None

        public_objs = [(name, inspect.unwrap(obj))
                       for name, obj in inspect.getmembers(self.obj)
                       # Filter only *own* members. The rest are inherited
                       # in Class._fill_inheritance()
                       if (name in self.obj.__dict__ and
                           (_is_public(name) or name == '__init__') and
                           not forced_out(name))]

        # Convert the public Python objects to documentation objects.
        for name, obj in public_objs:
            if name in self.doc and self.doc[name].docstring:
                continue
            if inspect.ismethod(obj) or inspect.isfunction(obj):
                self.doc[name] = Function(
                    name, self.module, obj, cls=self,
                    method=not self._method_type(self.obj, name))
            elif (inspect.isdatadescriptor(obj) or
                  inspect.isgetsetdescriptor(obj) or
                  inspect.ismemberdescriptor(obj)):
                self.doc[name] = Variable(
                    name, self.module, inspect.getdoc(obj),
                    obj=getattr(obj, 'fget', obj),
                    cls=self, instance_var=True)
            elif not inspect.isroutine(obj):
                self.doc[name] = Variable(
                    name, self.module,
                    docstring=isinstance(obj, type) and inspect.getdoc(obj) or "",
                    cls=self,
                    instance_var=name in getattr(self.obj, "__slots__", ()))

    @staticmethod
    def _method_type(cls: type, name: str):
        """
        Returns `None` if the method `name` of class `cls`
        is a regular method. Otherwise, it returns
        `classmethod` or `staticmethod`, as appropriate.
        """
        func = getattr(cls, name, None)
        if inspect.ismethod(func):
            # If the function is already bound, it's a classmethod.
            # Regular methods are not bound before initialization.
            return classmethod
        for c in inspect.getmro(cls):
            if name in c.__dict__:
                if isinstance(c.__dict__[name], staticmethod):
                    return staticmethod
                return None
        raise RuntimeError("{}.{} not found".format(cls, name))

    @property
    def refname(self):
        return self.module.name + '.' + self.qualname

    def mro(self):
        """
        Returns a list of ancestor (superclass) documentation objects
        in method resolution order.

        The list will contain objects of type `pdoc.Class`
        if the types are documented, and `pdoc.External` otherwise.
        """
        return [self.module.find_class(c)
                for c in inspect.getmro(self.obj)
                if c not in (self.obj, object)]

    def subclasses(self):
        """
        Returns a list of subclasses of this class that are visible to the
        Python interpreter (obtained from type.__subclasses__()).

        The objects in the list are of type `pdoc.Class` if available,
        and `pdoc.External` otherwise.
        """
        return [self.module.find_class(c)
                for c in self.obj.__subclasses__()]

    def _filter_doc_objs(self, include_inherited=True, filter_func=lambda x: True):
        return sorted(obj for obj in self.doc.values()
                      if ((include_inherited or not obj.inherits) and
                          filter_func(obj) and
                          self.module._docfilter(obj)))  # TODO check if this needed

    def class_variables(self, include_inherited=True):
        """
        Returns all documented class variables in the class, sorted
        alphabetically as a list of `pdoc.Variable`.
        """
        return self._filter_doc_objs(
            include_inherited,
            lambda var: isinstance(var, Variable) and not var.instance_var)

    def instance_variables(self, include_inherited=True):
        """
        Returns all instance variables in the class, sorted
        alphabetically as a list of `pdoc.Variable`. Instance variables
        are attributes of `self` defined in a class's `__init__`
        method.
        """
        return self._filter_doc_objs(
            include_inherited,
            lambda var: isinstance(var, Variable) and var.instance_var)

    def methods(self, include_inherited=True):
        """
        Returns all documented methods as `pdoc.Function` objects in
        the class, sorted alphabetically with `__init__` always coming
        first.

        Unfortunately, this also includes class methods.
        """
        return self._filter_doc_objs(
            include_inherited,
            lambda f: isinstance(f, Function) and f.method)

    def functions(self, include_inherited=True):
        """
        Returns all documented static functions as `pdoc.Function`
        objects in the class, sorted alphabetically.
        """
        return self._filter_doc_objs(
            include_inherited,
            lambda f: isinstance(f, Function) and not f.method)

    def _fill_inheritance(self):
        """
        Traverses this class's ancestor list and attempts to fill in
        missing documentation from its ancestor's documentation.

        The first pass connects variables, methods and functions with
        their inherited couterparts. (The templates will decide how to
        display docstrings.) The second pass attempts to add instance
        variables to this class that were only explicitly declared in
        a parent class. This second pass is necessary since instance
        variables are only discoverable by traversing the abstract
        syntax tree.
        """
        mro = [c for c in self.mro() if isinstance(c, Class)]

        super_members = {}
        for cls in mro:
            for name, dobj in cls.doc.items():
                if name not in super_members and dobj.docstring:
                    super_members[name] = dobj
        for name, parent_dobj in super_members.items():
            if name not in self.doc:
                self.doc[name] = copy(parent_dobj)
            dobj = self.doc[name]
            if (dobj.obj is parent_dobj.obj or
                    not dobj.docstring or
                    dobj.docstring == parent_dobj.docstring):
                dobj.inherits = parent_dobj


class Function(Doc):
    """
    Representation of documentation for a Python function or method.
    """

    def __init__(self, name, module, func_obj, cls=None, method=False):
        """
        Same as `pdoc.Doc.__init__`, except `func_obj` must be a
        Python function object. The docstring is gathered automatically.

        `cls` should be set when this is a method or a static function
        beloing to a class. `cls` should be a `pdoc.Class` object.

        `method` should be `True` when the function is a method. In
        all other cases, it should be `False`.
        """
        super().__init__(name, module, func_obj)

        self.cls = cls
        """
        The `pdoc.Class` documentation object if the function is a method.
        If not, this is None.
        """

        self.method = method
        """
        Whether this function is a normal bound method.

        In particular, static and class methods have this set to False.
        """

    def funcdef(self):
        """
        Generates the string of keywords used to define the function, for example `def` or
        `async def`.
        """
        return 'async def' if self._is_async else 'def'

    @property
    def _is_async(self):
        """
        Returns whether is function is asynchronous, either as a coroutine or an async
        generator.
        """
        try:
            # Both of these are required because coroutines aren't classified as async
            # generators and vice versa.
            obj = inspect.unwrap(self.obj)
            return (inspect.iscoroutinefunction(obj) or
                    inspect.isasyncgenfunction(obj))
        except AttributeError:
            return False

    def params(self):
        """
        Returns a list where each element is a nicely formatted
        parameter of this function. This includes argument lists,
        keyword arguments and default values.
        """
        try:
            s = inspect.getfullargspec(inspect.unwrap(self.obj))
        except TypeError:
            # I guess this is for C builtin functions?
            return ["..."]

        # TODO: Optionally skip non-public "_params"
        params = []
        for i, param in enumerate(s.args):
            if s.defaults is not None and len(s.args) - i <= len(s.defaults):
                defind = len(s.defaults) - (len(s.args) - i)
                params.append("%s=%s" % (param, repr(s.defaults[defind])))
            else:
                params.append(param)
        if s.varargs is not None:
            params.append("*%s" % s.varargs)

        kwonlyargs = getattr(s, "kwonlyargs", None)
        if kwonlyargs:
            if s.varargs is None:
                params.append("*")
            for param in kwonlyargs:
                try:
                    params.append("%s=%s" % (param, repr(s.kwonlydefaults[param])))
                except KeyError:
                    params.append(param)

        keywords = getattr(s, "varkw", getattr(s, "keywords", None))
        if keywords is not None:
            params.append("**%s" % keywords)
        # TODO: The only thing now missing for Python 3 are type annotations
        return params

    def __lt__(self, other):
        # Push __init__ to the top.
        return self.name == '__init__' or super().__lt__(other)

    @property
    def refname(self):
        return (self.cls.refname if self.cls else self.module.refname) + '.' + self.name


class Variable(Doc):
    """
    Representation of a variable's documentation. This includes
    module, class and instance variables.
    """

    def __init__(self, name, module, docstring, *, obj=None, cls=None, instance_var=False):
        """
        Same as `pdoc.Doc.__init__`, except `cls` should be provided
        as a `pdoc.Class` object when this is a class or instance
        variable.
        """
        super().__init__(name, module, obj, docstring)

        self.cls = cls
        """
        The `podc.Class` object if this is a class or instance
        variable. If not, this is None.
        """

        self.instance_var = instance_var
        """
        True if variable is some class' instance variable (as
        opposed to class variable).
        """

    @property
    def qualname(self):
        if self.cls:
            return self.cls.qualname + '.' + self.name
        return self.name

    @property
    def refname(self):
        return (self.cls.refname if self.cls else self.module.refname) + '.' + self.name


class External(Doc):
    """
    A representation of an external identifier. The textual
    representation is the same as an internal identifier, but without
    any context. (Usually this makes linking more difficult.)

    External identifiers are also used to represent something that is
    not exported but appears somewhere in the public interface (like
    the ancestor list of a class).
    """

    __pdoc__[
        "External.docstring"
    ] = """
        An empty string. External identifiers do not have
        docstrings.
        """
    __pdoc__[
        "External.module"
    ] = """
        Always `None`. External identifiers have no associated
        `pdoc.Module`.
        """
    __pdoc__[
        "External.name"
    ] = """
        Always equivalent to `pdoc.External.refname` since external
        identifiers are always expressed in their fully qualified
        form.
        """

    def __init__(self, name):
        """
        Initializes an external identifier with `name`, where `name`
        should be a fully qualified name.
        """
        super().__init__(name, None, None)

    def url(self, *args, **kwargs):
        return '/%s.ext' % self.name
