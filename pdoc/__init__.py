"""
Python package `pdoc` provides types, functions, and a command-line
interface for accessing public documentation of Python modules, and
for presenting it in a user-friendly, industry-standard open format.
It is best suited for small- to medium-sized projects with tidy,
hierarchical APIs.

.. include:: ./documentation.md
"""
import ast
import enum
import importlib.machinery
import importlib.util
import inspect
import os
import os.path as path
import re
import sys
import typing
from contextlib import contextmanager
from copy import copy
from functools import lru_cache, reduce, partial, wraps
from itertools import tee, groupby
from types import ModuleType
from typing import (  # noqa: F401
    cast, Any, Callable, Dict, Generator, Iterable, List, Mapping, NewType,
    Optional, Set, Tuple, Type, TypeVar, Union,
)
from warnings import warn

from mako.lookup import TemplateLookup
from mako.exceptions import TopLevelLookupException
from mako.template import Template

try:
    from pdoc._version import version as __version__  # noqa: F401
except ImportError:
    __version__ = '???'  # Package not installed


_get_type_hints = lru_cache()(typing.get_type_hints)

_URL_MODULE_SUFFIX = '.html'
_URL_INDEX_MODULE_SUFFIX = '.m.html'  # For modules named literal 'index'
_URL_PACKAGE_SUFFIX = '/index.html'

# type.__module__ can be None by the Python spec. In those cases, use this value
_UNKNOWN_MODULE = '?'

T = TypeVar('T', 'Module', 'Class', 'Function', 'Variable')

__pdoc__: Dict[str, Union[bool, str]] = {}

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
    tpl_lookup.directories.insert(0, path.join(os.getenv("XDG_CONFIG_HOME", ''), "pdoc"))


class Context(dict):
    """
    The context object that maps all documented identifiers
    (`pdoc.Doc.refname`) to their respective `pdoc.Doc` objects.

    You can pass an instance of `pdoc.Context` to `pdoc.Module` constructor.
    All `pdoc.Module` objects that share the same `pdoc.Context` will see
    (and be able to link in HTML to) each other's identifiers.

    If you don't pass your own `Context` instance to `Module` constructor,
    a global context object will be used.
    """
    __pdoc__['Context.__init__'] = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A surrogate so that the check in Module._link_inheritance()
        # "__pdoc__-overriden key {!r} does not exist" can see the object
        # (and not warn).
        self.blacklisted = getattr(args[0], 'blacklisted', set()) if args else set()


_global_context = Context()


def reset():
    """Resets the global `pdoc.Context` to the initial (empty) state."""
    global _global_context
    _global_context.clear()

    # Clear LRU caches
    for func in (_get_type_hints,
                 _is_blacklisted,
                 _is_whitelisted):
        func.cache_clear()
    for cls in (Doc, Module, Class, Function, Variable, External):
        for _, method in inspect.getmembers(cls):
            if isinstance(method, property):
                method = method.fget
            if hasattr(method, 'cache_clear'):
                method.cache_clear()


def _get_config(**kwargs):
    # Apply config.mako configuration
    MAKO_INTERNALS = Template('').module.__dict__.keys()
    DEFAULT_CONFIG = path.join(path.dirname(__file__), 'templates', 'config.mako')
    config = {}
    for config_module in (Template(filename=DEFAULT_CONFIG).module,
                          tpl_lookup.get_template('/config.mako').module):
        config.update((var, getattr(config_module, var, None))
                      for var in config_module.__dict__
                      if var not in MAKO_INTERNALS)

    known_keys = (set(config)
                  | {'docformat'}  # Feature. https://github.com/pdoc3/pdoc/issues/169
                  # deprecated
                  | {'module', 'modules', 'http_server', 'external_links', 'search_query'})
    invalid_keys = {k: v for k, v in kwargs.items() if k not in known_keys}
    if invalid_keys:
        warn(f'Unknown configuration variables (not in config.mako): {invalid_keys}')
    config.update(kwargs)

    if 'search_query' in config:
        warn('Option `search_query` has been deprecated. Use `google_search_query` instead',
             DeprecationWarning, stacklevel=2)
        config['google_search_query'] = config['search_query']
        del config['search_query']

    return config


def _render_template(template_name, **kwargs):
    """
    Returns the Mako template with the given name.  If the template
    cannot be found, a nicer error message is displayed.
    """
    config = _get_config(**kwargs)

    try:
        t = tpl_lookup.get_template(template_name)
    except TopLevelLookupException:
        paths = [path.join(p, template_name.lstrip('/')) for p in tpl_lookup.directories]
        raise OSError(f"No template found at any of: {', '.join(paths)}")

    try:
        return t.render(**config).strip()
    except Exception:
        from mako import exceptions
        print(exceptions.text_error_template().render(),
              file=sys.stderr)
        raise


def html(module_name, docfilter=None, reload=False, skip_errors=False, **kwargs) -> str:
    """
    Returns the documentation for the module `module_name` in HTML
    format. The module must be a module or an importable string.

    `docfilter` is an optional predicate that controls which
    documentation objects are shown in the output. It is a function
    that takes a single argument (a documentation object) and returns
    `True` or `False`. If `False`, that object will not be documented.
    """
    mod = Module(import_module(module_name, reload=reload),
                 docfilter=docfilter, skip_errors=skip_errors)
    link_inheritance()
    return mod.html(**kwargs)


def text(module_name, docfilter=None, reload=False, skip_errors=False, **kwargs) -> str:
    """
    Returns the documentation for the module `module_name` in plain
    text format suitable for viewing on a terminal.
    The module must be a module or an importable string.

    `docfilter` is an optional predicate that controls which
    documentation objects are shown in the output. It is a function
    that takes a single argument (a documentation object) and returns
    `True` or `False`. If `False`, that object will not be documented.
    """
    mod = Module(import_module(module_name, reload=reload),
                 docfilter=docfilter, skip_errors=skip_errors)
    link_inheritance()
    return mod.text(**kwargs)


def import_module(module: Union[str, ModuleType],
                  *, reload: bool = False) -> ModuleType:
    """
    Return module object matching `module` specification (either a python
    module path or a filesystem path to file/directory).
    """
    @contextmanager
    def _module_path(module):
        from os.path import abspath, dirname, isfile, isdir, split
        path = '_pdoc_dummy_nonexistent'
        module_name = inspect.getmodulename(module)
        if isdir(module):
            path, module = split(abspath(module))
        elif isfile(module) and module_name:
            path, module = dirname(abspath(module)), module_name
        try:
            sys.path.insert(0, path)
            yield module
        finally:
            sys.path.remove(path)

    if isinstance(module, Module):
        module = module.obj
    if isinstance(module, str):
        with _module_path(module) as module_path:
            try:
                module = importlib.import_module(module_path)
            except Exception as e:
                raise ImportError(f'Error importing {module!r}: {e.__class__.__name__}: {e}')

    assert inspect.ismodule(module)
    # If this is pdoc itself, return without reloading. Otherwise later
    # `isinstance(..., pdoc.Doc)` calls won't work correctly.
    if reload and not module.__name__.startswith(__name__):
        module = importlib.reload(module)
        # We recursively reload all submodules, in case __all_ is used - cf. issue #264
        for mod_key, mod in list(sys.modules.items()):
            if mod_key.startswith(module.__name__):
                importlib.reload(mod)
    return module


def _pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def _pep224_docstrings(doc_obj: Union['Module', 'Class'], *,
                       _init_tree=None) -> Tuple[Dict[str, str],
                                                 Dict[str, str]]:
    """
    Extracts PEP-224 docstrings and doc-comments (`#: ...`) for variables of `doc_obj`
    (either a `pdoc.Module` or `pdoc.Class`).

    Returns a tuple of two dicts mapping variable names to their docstrings.
    The second dict contains instance variables and is non-empty only in case
    `doc_obj` is a `pdoc.Class` which has `__init__` method.
    """
    # No variables in namespace packages
    if isinstance(doc_obj, Module) and doc_obj.is_namespace:
        return {}, {}

    vars: Dict[str, str] = {}
    instance_vars: Dict[str, str] = {}

    if _init_tree:
        tree = _init_tree
    else:
        try:
            # Maybe raise exceptions with appropriate message
            # before using cleaned doc_obj.source
            _ = inspect.findsource(doc_obj.obj)
            tree = ast.parse(doc_obj.source)  # type: ignore
        except (OSError, TypeError, SyntaxError) as exc:
            # Don't emit a warning for builtins that don't have source available
            is_builtin = getattr(doc_obj.obj, '__module__', None) == 'builtins'
            if not is_builtin:
                warn(f"Couldn't read PEP-224 variable docstrings from {doc_obj!r}: {exc}",
                     stacklevel=3 + int(isinstance(doc_obj, Class)))
            return {}, {}

        if isinstance(doc_obj, Class):
            tree = tree.body[0]  # ast.parse creates a dummy ast.Module wrapper

            # For classes, maybe add instance variables defined in __init__
            # Get the *last* __init__ node in case it is preceded by @overloads.
            for node in reversed(tree.body):
                if isinstance(node, ast.FunctionDef) and node.name == '__init__':
                    instance_vars, _ = _pep224_docstrings(doc_obj, _init_tree=node)
                    break

    def get_name(assign_node):
        if isinstance(assign_node, ast.Assign) and len(assign_node.targets) == 1:
            target = assign_node.targets[0]
        elif isinstance(assign_node, ast.AnnAssign):
            target = assign_node.target
            # Skip the annotation. PEP 526 says:
            # > Putting the instance variable annotations together in the class
            # > makes it easier to find them, and helps a first-time reader of the code.
        else:
            return None

        if not _init_tree and isinstance(target, ast.Name):
            name = target.id
        elif (_init_tree and
              isinstance(target, ast.Attribute) and
              isinstance(target.value, ast.Name) and
              target.value.id == 'self'):
            name = target.attr
        else:
            return None

        if not _is_public(name) and not _is_whitelisted(name, doc_obj):
            return None

        return name

    # For handling PEP-224 docstrings for variables
    for assign_node, str_node in _pairwise(ast.iter_child_nodes(tree)):
        if not (isinstance(assign_node, (ast.Assign, ast.AnnAssign)) and
                isinstance(str_node, ast.Expr) and
                isinstance(str_node.value, ast.Str)):
            continue

        name = get_name(assign_node)
        if not name:
            continue

        docstring = inspect.cleandoc(str_node.value.s).strip()
        if not docstring:
            continue

        vars[name] = docstring

    # For handling '#:' docstrings for variables
    for assign_node in ast.iter_child_nodes(tree):
        if not isinstance(assign_node, (ast.Assign, ast.AnnAssign)):
            continue

        name = get_name(assign_node)
        if not name:
            continue

        # Already documented. PEP-224 method above takes precedence.
        if name in vars:
            continue

        def get_indent(line):
            return len(line) - len(line.lstrip())

        source_lines = doc_obj.source.splitlines()  # type: ignore
        assign_line = source_lines[assign_node.lineno - 1]
        assign_indent = get_indent(assign_line)
        comment_lines = []
        MARKER = '#: '
        for line in reversed(source_lines[:assign_node.lineno - 1]):
            if get_indent(line) == assign_indent and line.lstrip().startswith(MARKER):
                comment_lines.append(line.split(MARKER, maxsplit=1)[1])
            else:
                break

        # Since we went 'up' need to reverse lines to be in correct order
        comment_lines = comment_lines[::-1]

        # Finally: check for a '#: ' comment at the end of the assignment line itself.
        if MARKER in assign_line:
            comment_lines.append(assign_line.rsplit(MARKER, maxsplit=1)[1])

        if comment_lines:
            vars[name] = '\n'.join(comment_lines)

    return vars, instance_vars


@lru_cache()
def _is_whitelisted(name: str, doc_obj: Union['Module', 'Class']):
    """
    Returns `True` if `name` (relative or absolute refname) is
    contained in some module's __pdoc__ with a truish value.
    """
    refname = f'{doc_obj.refname}.{name}'
    module: Optional[Module] = doc_obj.module
    while module:
        qualname = refname[len(module.refname) + 1:]
        if module.__pdoc__.get(qualname) or module.__pdoc__.get(refname):
            return True
        module = module.supermodule
    return False


@lru_cache()
def _is_blacklisted(name: str, doc_obj: Union['Module', 'Class']):
    """
    Returns `True` if `name` (relative or absolute refname) is
    contained in some module's __pdoc__ with value False.
    """
    refname = f'{doc_obj.refname}.{name}'
    module: Optional[Module] = doc_obj.module
    while module:
        qualname = refname[len(module.refname) + 1:]
        if module.__pdoc__.get(qualname) is False or module.__pdoc__.get(refname) is False:
            return True
        module = module.supermodule
    return False


def _is_public(ident_name):
    """
    Returns `True` if `ident_name` matches the export criteria for an
    identifier name.
    """
    return not ident_name.startswith("_")


def _is_function(obj):
    return inspect.isroutine(obj) and callable(obj)


def _is_descriptor(obj):
    return (inspect.isdatadescriptor(obj) or
            inspect.ismethoddescriptor(obj) or
            inspect.isgetsetdescriptor(obj) or
            inspect.ismemberdescriptor(obj))


def _filter_type(type: Type[T],
                 values: Union[Iterable['Doc'], Mapping[str, 'Doc']]) -> List[T]:
    """
    Return a list of values from `values` of type `type`.
    """
    if isinstance(values, dict):
        values = values.values()
    return [i for i in values if isinstance(i, type)]


def _toposort(graph: Mapping[T, Set[T]]) -> Generator[T, None, None]:
    """
    Return items of `graph` sorted in topological order.
    Source: https://rosettacode.org/wiki/Topological_sort#Python
    """
    items_without_deps = reduce(set.union, graph.values(), set()) - set(graph.keys())  # type: ignore  # noqa: E501
    yield from items_without_deps
    ordered = items_without_deps
    while True:
        graph = {item: (deps - ordered)
                 for item, deps in graph.items()
                 if item not in ordered}
        ordered = {item
                   for item, deps in graph.items()
                   if not deps}
        yield from ordered
        if not ordered:
            break
    assert not graph, f"A cyclic dependency exists amongst {graph!r}"


def link_inheritance(context: Context = None):
    """
    Link inheritance relationsships between `pdoc.Class` objects
    (and between their members) of all `pdoc.Module` objects that
    share the provided `context` (`pdoc.Context`).

    You need to call this if you expect `pdoc.Doc.inherits` and
    inherited `pdoc.Doc.docstring` to be set correctly.
    """
    if context is None:
        context = _global_context

    graph = {cls: set(cls.mro(only_documented=True))
             for cls in _filter_type(Class, context)}

    for cls in _toposort(graph):
        cls._fill_inheritance()

    for module in _filter_type(Module, context):
        module._link_inheritance()


class Doc:
    """
    A base class for all documentation objects.

    A documentation object corresponds to *something* in a Python module
    that has a docstring associated with it. Typically, this includes
    modules, classes, functions, and methods. However, `pdoc` adds support
    for extracting some docstrings from abstract syntax trees, making
    (module, class or instance) variables supported too.

    A special type of documentation object `pdoc.External` is used to
    represent identifiers that are not part of the public interface of
    a module. (The name "External" is a bit of a misnomer, since it can
    also correspond to unexported members of the module, particularly in
    a class's ancestor list.)
    """
    __slots__ = ('module', 'name', 'obj', 'docstring', 'inherits')

    def __init__(self, name: str, module, obj, docstring: str = None):
        """
        Initializes a documentation object, where `name` is the public
        identifier name, `module` is a `pdoc.Module` object where raw
        Python object `obj` is defined, and `docstring` is its
        documentation string. If `docstring` is left empty, it will be
        read with `inspect.getdoc()`.
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

        docstring = (docstring or inspect.getdoc(obj) or '').strip()
        if '.. include::' in docstring:
            from pdoc.html_helpers import _ToMarkdown
            docstring = _ToMarkdown.admonitions(docstring, self.module, ('include',))
        self.docstring = docstring
        """
        The cleaned docstring for this object with any `.. include::`
        directives resolved (i.e. content included).
        """

        self.inherits: Optional[Union[Class, Function, Variable]] = None
        """
        The Doc object (Class, Function, or Variable) this object inherits from,
        if any.
        """

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.refname!r}>'

    @property  # type: ignore
    @lru_cache()
    def source(self) -> str:
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
    def refname(self) -> str:
        """
        Reference name of this documentation
        object, usually its fully qualified path
        (e.g. <code>pdoc.Doc.refname</code>). Every
        documentation object provides this property.
        """
        # Ok for Module and External, the rest need it overriden
        return self.name

    @property
    def qualname(self) -> str:
        """
        Module-relative "qualified" name of this documentation
        object, used for show (e.g. <code>Doc.qualname</code>).
        """
        return getattr(self.obj, '__qualname__', self.name)

    @lru_cache()
    def url(self, relative_to: 'Module' = None, *, link_prefix: str = '',
            top_ancestor: bool = False) -> str:
        """
        Canonical relative URL (including page fragment) for this
        documentation object.

        Specify `relative_to` (a `pdoc.Module` object) to obtain a
        relative URL.

        For usage of `link_prefix` see `pdoc.html()`.

        If `top_ancestor` is `True`, the returned URL instead points to
        the top ancestor in the object's `pdoc.Doc.inherits` chain.
        """
        if top_ancestor:
            self = self._inherits_top()

        if relative_to is None or link_prefix:
            return link_prefix + self._url()

        if self.module.name == relative_to.name:
            return f'#{self.refname}'

        # Otherwise, compute relative path from current module to link target
        url = os.path.relpath(self._url(), relative_to.url()).replace(path.sep, '/')
        # We have one set of '..' too many
        if url.startswith('../'):
            url = url[3:]
        return url

    def _url(self):
        return f'{self.module._url()}#{self.refname}'

    def _inherits_top(self):
        """
        Follow the `pdoc.Doc.inherits` chain and return the top object.
        """
        top = self
        while top.inherits:
            top = top.inherits
        return top

    def __lt__(self, other):
        return self.refname < other.refname


class Module(Doc):
    """
    Representation of a module's documentation.
    """
    __pdoc__["Module.name"] = """
        The name of this module with respect to the context/path in which
        it was imported from. It is always an absolute import path.
        """

    __slots__ = ('supermodule', 'doc', '_context', '_is_inheritance_linked',
                 '_skipped_submodules')

    def __init__(self, module: Union[ModuleType, str], *, docfilter: Callable[[Doc], bool] = None,
                 supermodule: 'Module' = None, context: Context = None,
                 skip_errors: bool = False):
        """
        Creates a `Module` documentation object given the actual
        module Python object.

        `docfilter` is an optional predicate that controls which
        sub-objects are documentated (see also: `pdoc.html()`).

        `supermodule` is the parent `pdoc.Module` this module is
        a submodule of.

        `context` is an instance of `pdoc.Context`. If `None` a
        global context object will be used.

        If `skip_errors` is `True` and an unimportable, erroneous
        submodule is encountered, a warning will be issued instead
        of raising an exception.
        """
        if isinstance(module, str):
            module = import_module(module)

        super().__init__(module.__name__, self, module)
        if self.name.endswith('.__init__') and not self.is_package:
            self.name = self.name[:-len('.__init__')]

        self._context = _global_context if context is None else context
        """
        A lookup table for ALL doc objects of all modules that share this context,
        mainly used in `Module.find_ident()`.
        """
        assert isinstance(self._context, Context), \
            'pdoc.Module(context=) should be a pdoc.Context instance'

        self.supermodule = supermodule
        """
        The parent `pdoc.Module` this module is a submodule of, or `None`.
        """

        self.doc: Dict[str, Union[Module, Class, Function, Variable]] = {}
        """A mapping from identifier name to a documentation object."""

        self._is_inheritance_linked = False
        """Re-entry guard for `pdoc.Module._link_inheritance()`."""

        self._skipped_submodules = set()

        var_docstrings, _ = _pep224_docstrings(self)

        # Populate self.doc with this module's public members
        public_objs = []
        if hasattr(self.obj, '__all__'):
            for name in self.obj.__all__:
                try:
                    obj = getattr(self.obj, name)
                except AttributeError:
                    warn(f"Module {self.module!r} doesn't contain identifier `{name}` "
                         "exported in `__all__`")
                if not _is_blacklisted(name, self):
                    obj = inspect.unwrap(obj)
                public_objs.append((name, obj))
        else:
            def is_from_this_module(obj):
                mod = inspect.getmodule(inspect.unwrap(obj))
                return mod is None or mod.__name__ == self.obj.__name__

            for name, obj in inspect.getmembers(self.obj):
                if ((_is_public(name) or
                     _is_whitelisted(name, self)) and
                        (_is_blacklisted(name, self) or  # skips unwrapping that follows
                         is_from_this_module(obj) or
                         name in var_docstrings)):

                    if _is_blacklisted(name, self):
                        self._context.blacklisted.add(f'{self.refname}.{name}')
                        continue

                    obj = inspect.unwrap(obj)
                    public_objs.append((name, obj))

            index = list(self.obj.__dict__).index
            public_objs.sort(key=lambda i: index(i[0]))

        for name, obj in public_objs:
            if _is_function(obj):
                self.doc[name] = Function(name, self, obj)
            elif inspect.isclass(obj):
                self.doc[name] = Class(name, self, obj)
            elif name in var_docstrings:
                self.doc[name] = Variable(name, self, var_docstrings[name], obj=obj)

        # If the module is a package, scan the directory for submodules
        if self.is_package:

            def iter_modules(paths):
                """
                Custom implementation of `pkgutil.iter_modules()`
                because that one doesn't play well with namespace packages.
                See: https://github.com/pypa/setuptools/issues/83
                """
                from os.path import isdir, join
                for pth in paths:
                    for file in os.listdir(pth):
                        if file.startswith(('.', '__pycache__', '__init__.py')):
                            continue
                        module_name = inspect.getmodulename(file)
                        if module_name:
                            yield module_name
                        if isdir(join(pth, file)) and '.' not in file:
                            yield file

            for root in iter_modules(self.obj.__path__):
                # Ignore if this module was already doc'd.
                if root in self.doc:
                    continue

                # Ignore if it isn't exported
                if not _is_public(root) and not _is_whitelisted(root, self):
                    continue
                if _is_blacklisted(root, self):
                    self._skipped_submodules.add(root)
                    continue

                assert self.refname == self.name
                fullname = f"{self.name}.{root}"
                try:
                    m = Module(import_module(fullname),
                               docfilter=docfilter, supermodule=self,
                               context=self._context, skip_errors=skip_errors)
                except Exception as ex:
                    if skip_errors:
                        warn(str(ex), Module.ImportWarning)
                        continue
                    raise

                self.doc[root] = m
                # Skip empty namespace packages because they may
                # as well be other auxiliary directories
                if m.is_namespace and not m.doc:
                    del self.doc[root]
                    self._context.pop(m.refname)

        # Apply docfilter
        if docfilter:
            for name, dobj in self.doc.copy().items():
                if not docfilter(dobj):
                    self.doc.pop(name)
                    self._context.pop(dobj.refname, None)

        # Build the reference name dictionary of the module
        self._context[self.refname] = self
        for docobj in self.doc.values():
            self._context[docobj.refname] = docobj
            if isinstance(docobj, Class):
                self._context.update((obj.refname, obj)
                                     for obj in docobj.doc.values())

    class ImportWarning(UserWarning):
        """
        Our custom import warning because the builtin is ignored by default.
        https://docs.python.org/3/library/warnings.html#default-warning-filter
        """

    __pdoc__['Module.ImportWarning'] = False

    @property
    def __pdoc__(self) -> dict:
        """This module's __pdoc__ dict, or an empty dict if none."""
        return getattr(self.obj, '__pdoc__', {})

    def _link_inheritance(self):
        # Inherited members are already in place since
        # `Class._fill_inheritance()` has been called from
        # `pdoc.fill_inheritance()`.
        # Now look for docstrings in the module's __pdoc__ override.

        if self._is_inheritance_linked:
            # Prevent re-linking inheritance for modules which have already
            # had done so. Otherwise, this would raise "does not exist"
            # errors if `pdoc.link_inheritance()` is called multiple times.
            return

        # Apply __pdoc__ overrides
        for name, docstring in self.__pdoc__.items():
            # In case of whitelisting with "True", there's nothing to do
            if docstring is True:
                continue

            refname = f"{self.refname}.{name}"
            if docstring in (False, None):
                if docstring is None:
                    warn('Setting `__pdoc__[key] = None` is deprecated; '
                         'use `__pdoc__[key] = False` '
                         f'(key: {name!r}, module: {self.name!r}).')

                if name in self._skipped_submodules:
                    continue

                if (not name.endswith('.__init__') and
                        name not in self.doc and
                        refname not in self._context and
                        refname not in self._context.blacklisted):
                    warn(f'__pdoc__-overriden key {name!r} does not exist '
                         f'in module {self.name!r}')

                obj = self.find_ident(name)
                cls = getattr(obj, 'cls', None)
                if cls:
                    del cls.doc[obj.name]
                self.doc.pop(name, None)
                self._context.pop(refname, None)

                # Pop also all that startwith refname
                for key in list(self._context.keys()):
                    if key.startswith(refname + '.'):
                        del self._context[key]

                continue

            dobj = self.find_ident(refname)
            if isinstance(dobj, External):
                continue
            if not isinstance(docstring, str):
                raise ValueError('__pdoc__ dict values must be strings; '
                                 f'__pdoc__[{name!r}] is of type {type(docstring)}')
            dobj.docstring = inspect.cleandoc(docstring)

        # Now after docstrings are set correctly, continue the
        # inheritance routine, marking members inherited or not
        for c in _filter_type(Class, self.doc):
            c._link_inheritance()

        self._is_inheritance_linked = True

    def text(self, **kwargs) -> str:
        """
        Returns the documentation for this module as plain text.
        """
        txt = _render_template('/text.mako', module=self, **kwargs)
        return re.sub("\n\n\n+", "\n\n", txt)

    def html(self, minify=True, **kwargs) -> str:
        """
        Returns the documentation for this module as
        self-contained HTML.

        If `minify` is `True`, the resulting HTML is minified.

        For explanation of other arguments, see `pdoc.html()`.

        `kwargs` is passed to the `mako` render function.
        """
        html = _render_template('/html.mako', module=self, **kwargs)
        if minify:
            from pdoc.html_helpers import minify_html
            html = minify_html(html)
        return html

    @property
    def is_package(self) -> bool:
        """
        `True` if this module is a package.

        Works by checking whether the module has a `__path__` attribute.
        """
        return hasattr(self.obj, "__path__")

    @property
    def is_namespace(self) -> bool:
        """
        `True` if this module is a namespace package.
        """
        try:
            return self.obj.__spec__.origin in (None, 'namespace')  # None in Py3.7+
        except AttributeError:
            return False

    def find_class(self, cls: type) -> Doc:
        """
        Given a Python `cls` object, try to find it in this module
        or in any of the exported identifiers of the submodules.
        """
        # XXX: Is this corrent? Does it always match
        # `Class.module.name + Class.qualname`?. Especially now?
        # If not, see what was here before.
        return self.find_ident(f'{cls.__module__ or _UNKNOWN_MODULE}.{cls.__qualname__}')

    def find_ident(self, name: str) -> Doc:
        """
        Searches this module and **all** other public modules
        for an identifier with name `name` in its list of
        exported identifiers.

        The documentation object corresponding to the identifier is
        returned. If one cannot be found, then an instance of
        `External` is returned populated with the given identifier.
        """
        _name = name.rstrip('()')  # Function specified with parentheses

        if _name.endswith('.__init__'):  # Ref to class' init is ref to class itself
            _name = _name[:-len('.__init__')]

        return (self.doc.get(_name) or
                self._context.get(_name) or
                self._context.get(f'{self.name}.{_name}') or
                External(name))

    def _filter_doc_objs(self, type: Type[T], sort=True) -> List[T]:
        result = _filter_type(type, self.doc)
        return sorted(result) if sort else result

    def variables(self, sort=True) -> List['Variable']:
        """
        Returns all documented module-level variables in the module,
        optionally sorted alphabetically, as a list of `pdoc.Variable`.
        """
        return self._filter_doc_objs(Variable, sort)

    def classes(self, sort=True) -> List['Class']:
        """
        Returns all documented module-level classes in the module,
        optionally sorted alphabetically, as a list of `pdoc.Class`.
        """
        return self._filter_doc_objs(Class, sort)

    def functions(self, sort=True) -> List['Function']:
        """
        Returns all documented module-level functions in the module,
        optionally sorted alphabetically, as a list of `pdoc.Function`.
        """
        return self._filter_doc_objs(Function, sort)

    def submodules(self) -> List['Module']:
        """
        Returns all documented sub-modules of the module sorted
        alphabetically as a list of `pdoc.Module`.
        """
        return self._filter_doc_objs(Module)

    def _url(self):
        url = self.module.name.replace('.', '/')
        if self.is_package:
            return url + _URL_PACKAGE_SUFFIX
        elif url.endswith('/index'):
            return url + _URL_INDEX_MODULE_SUFFIX
        return url + _URL_MODULE_SUFFIX


def _getmembers_all(obj: type) -> List[Tuple[str, Any]]:
    # The following code based on inspect.getmembers() @ 5b23f7618d43
    mro = obj.__mro__[:-1]  # Skip object
    names = set(dir(obj))
    # Add keys from bases
    for base in mro:
        names.update(base.__dict__.keys())
        # Add members for which type annotations exist
        names.update(getattr(obj, '__annotations__', {}).keys())

    results = []
    for name in names:
        try:
            value = getattr(obj, name)
        except AttributeError:
            for base in mro:
                if name in base.__dict__:
                    value = base.__dict__[name]
                    break
            else:
                # Missing slot member or a buggy __dir__;
                # In out case likely a type-annotated member
                # which we'll interpret as a variable
                value = None
        results.append((name, value))
    return results


class Class(Doc):
    """
    Representation of a class' documentation.
    """
    __slots__ = ('doc', '_super_members')

    def __init__(self, name: str, module: Module, obj, *, docstring: str = None):
        assert inspect.isclass(obj)

        if docstring is None:
            init_doc = inspect.getdoc(obj.__init__) or ''
            if init_doc == object.__init__.__doc__:
                init_doc = ''
            docstring = f'{inspect.getdoc(obj) or ""}\n\n{init_doc}'.strip()

        super().__init__(name, module, obj, docstring=docstring)

        self.doc: Dict[str, Union[Function, Variable]] = {}
        """A mapping from identifier name to a `pdoc.Doc` objects."""

        # Annotations for filtering.
        # Use only own, non-inherited annotations (the rest will be inherited)
        annotations = getattr(self.obj, '__annotations__', {})

        public_objs = []
        for _name, obj in _getmembers_all(self.obj):
            # Filter only *own* members. The rest are inherited
            # in Class._fill_inheritance()
            if ((_name in self.obj.__dict__ or
                 _name in annotations) and
                    (_is_public(_name) or
                     _is_whitelisted(_name, self))):

                if _is_blacklisted(_name, self):
                    self.module._context.blacklisted.add(f'{self.refname}.{_name}')
                    continue

                obj = inspect.unwrap(obj)
                public_objs.append((_name, obj))

        def definition_order_index(
                name,
                _annot_index=list(annotations).index,
                _dict_index=list(self.obj.__dict__).index):
            try:
                return _dict_index(name)
            except ValueError:
                pass
            try:
                return _annot_index(name) - len(annotations)  # sort annotated first
            except ValueError:
                return 9e9

        public_objs.sort(key=lambda i: definition_order_index(i[0]))

        var_docstrings, instance_var_docstrings = _pep224_docstrings(self)

        # Convert the public Python objects to documentation objects.
        for name, obj in public_objs:
            if _is_function(obj):
                self.doc[name] = Function(
                    name, self.module, obj, cls=self)
            else:
                self.doc[name] = Variable(
                    name, self.module,
                    docstring=(
                        var_docstrings.get(name) or
                        (inspect.isclass(obj) or _is_descriptor(obj)) and inspect.getdoc(obj)),
                    cls=self,
                    obj=getattr(obj, 'fget', getattr(obj, '__get__', None)),
                    instance_var=(_is_descriptor(obj) or
                                  name in getattr(self.obj, '__slots__', ())))

        for name, docstring in instance_var_docstrings.items():
            self.doc[name] = Variable(
                name, self.module, docstring, cls=self,
                obj=getattr(self.obj, name, None),
                instance_var=True)

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
        raise RuntimeError(f"{cls}.{name} not found")

    @property
    def refname(self) -> str:
        return f'{self.module.name}.{self.qualname}'

    def mro(self, only_documented=False) -> List['Class']:
        """
        Returns a list of ancestor (superclass) documentation objects
        in method resolution order.

        The list will contain objects of type `pdoc.Class`
        if the types are documented, and `pdoc.External` otherwise.
        """
        classes = [cast(Class, self.module.find_class(c))
                   for c in inspect.getmro(self.obj)
                   if c not in (self.obj, object)]
        if self in classes:
            # This can contain self in case of a class inheriting from
            # a class with (previously) the same name. E.g.
            #
            #     class Loc(namedtuple('Loc', 'lat lon')): ...
            #
            # We remove it from ancestors so that toposort doesn't break.
            classes.remove(self)
        if only_documented:
            classes = _filter_type(Class, classes)
        return classes

    def subclasses(self) -> List['Class']:
        """
        Returns a list of subclasses of this class that are visible to the
        Python interpreter (obtained from `type.__subclasses__()`).

        The objects in the list are of type `pdoc.Class` if available,
        and `pdoc.External` otherwise.
        """
        return sorted(cast(Class, self.module.find_class(c))
                      for c in type.__subclasses__(self.obj))

    def params(self, *, annotate=False, link=None) -> List[str]:
        """
        Return a list of formatted parameters accepted by the
        class constructor (method `__init__`). See `pdoc.Function.params`.
        """
        name = self.name + '.__init__'
        qualname = self.qualname + '.__init__'
        refname = self.refname + '.__init__'
        exclusions = self.module.__pdoc__
        if name in exclusions or qualname in exclusions or refname in exclusions:
            return []

        return Function._params(self, annotate=annotate, link=link, module=self.module)

    def _filter_doc_objs(self, type: Type[T], include_inherited=True,
                         filter_func: Callable[[T], bool] = lambda x: True,
                         sort=True) -> List[T]:
        result = [obj for obj in _filter_type(type, self.doc)
                  if (include_inherited or not obj.inherits) and filter_func(obj)]
        return sorted(result) if sort else result

    def class_variables(self, include_inherited=True, sort=True) -> List['Variable']:
        """
        Returns an optionally-sorted list of `pdoc.Variable` objects that
        represent this class' class variables.
        """
        return self._filter_doc_objs(
            Variable, include_inherited, lambda dobj: not dobj.instance_var,
            sort)

    def instance_variables(self, include_inherited=True, sort=True) -> List['Variable']:
        """
        Returns an optionally-sorted list of `pdoc.Variable` objects that
        represent this class' instance variables. Instance variables
        are those defined in a class's `__init__` as `self.variable = ...`.
        """
        return self._filter_doc_objs(
            Variable, include_inherited, lambda dobj: dobj.instance_var,
            sort)

    def methods(self, include_inherited=True, sort=True) -> List['Function']:
        """
        Returns an optionally-sorted list of `pdoc.Function` objects that
        represent this class' methods.
        """
        return self._filter_doc_objs(
            Function, include_inherited, lambda dobj: dobj.is_method,
            sort)

    def functions(self, include_inherited=True, sort=True) -> List['Function']:
        """
        Returns an optionally-sorted list of `pdoc.Function` objects that
        represent this class' static functions.
        """
        return self._filter_doc_objs(
            Function, include_inherited, lambda dobj: not dobj.is_method,
            sort)

    def inherited_members(self) -> List[Tuple['Class', List[Doc]]]:
        """
        Returns all inherited members as a list of tuples
        (ancestor class, list of ancestor class' members sorted by name),
        sorted by MRO.
        """
        return sorted(((cast(Class, k), sorted(g))
                       for k, g in groupby((i.inherits
                                            for i in self.doc.values() if i.inherits),
                                           key=lambda i: i.cls)),                   # type: ignore
                      key=lambda x, _mro_index=self.mro().index: _mro_index(x[0]))  # type: ignore

    def _fill_inheritance(self):
        """
        Traverses this class's ancestor list and attempts to fill in
        missing documentation objects from its ancestors.

        Afterwards, call to `pdoc.Class._link_inheritance()` to also
        set `pdoc.Doc.inherits` pointers.
        """
        super_members = self._super_members = {}
        for cls in self.mro(only_documented=True):
            for name, dobj in cls.doc.items():
                if name not in super_members and dobj.docstring:
                    super_members[name] = dobj
                    if name not in self.doc:
                        dobj = copy(dobj)
                        dobj.cls = self

                        self.doc[name] = dobj
                        self.module._context[dobj.refname] = dobj

    def _link_inheritance(self):
        """
        Set `pdoc.Doc.inherits` pointers to inherited ancestors' members,
        as appropriate. This must be called after
        `pdoc.Class._fill_inheritance()`.

        The reason this is split in two parts is that in-between
        the `__pdoc__` overrides are applied.
        """
        if not hasattr(self, '_super_members'):
            return

        for name, parent_dobj in self._super_members.items():
            try:
                dobj = self.doc[name]
            except KeyError:
                # There is a key in some __pdoc__ dict blocking this member
                continue
            if (dobj.obj is parent_dobj.obj or
                    (dobj.docstring or parent_dobj.docstring) == parent_dobj.docstring):
                dobj.inherits = parent_dobj
                dobj.docstring = parent_dobj.docstring
        del self._super_members


def maybe_lru_cache(func):
    cached_func = lru_cache()(func)

    @wraps(func)
    def wrapper(*args):
        try:
            return cached_func(*args)
        except TypeError:
            return func(*args)

    return wrapper


@maybe_lru_cache
def _formatannotation(annot):
    """
    Format typing annotation with better handling of `typing.NewType`,
    `typing.Optional`, `nptyping.NDArray` and other types.

    >>> _formatannotation(NewType('MyType', str))
    'MyType'
    >>> _formatannotation(Optional[Tuple[Optional[int], None]])
    'Optional[Tuple[Optional[int], None]]'
    """
    class force_repr(str):
        __repr__ = str.__str__

    def maybe_replace_reprs(a):
        # NoneType -> None
        if a is type(None):  # noqa: E721
            return force_repr('None')
        # Union[T, None] -> Optional[T]
        if (getattr(a, '__origin__', None) is typing.Union and
                len(a.__args__) == 2 and
                type(None) in a.__args__):
            t = inspect.formatannotation(
                maybe_replace_reprs(next(filter(None, a.__args__))))
            return force_repr(f'Optional[{t}]')
        # typing.NewType('T', foo) -> T
        module = getattr(a, '__module__', '')
        if module == 'typing' and getattr(a, '__qualname__', '').startswith('NewType.'):
            return force_repr(a.__name__)
        # nptyping.types._ndarray.NDArray -> NDArray[(Any,), Int[64]]  # GH-231
        if module.startswith('nptyping.'):
            return force_repr(repr(a))
        # Recurse into typing.Callable/etc. args
        if hasattr(a, 'copy_with') and hasattr(a, '__args__'):
            if a is typing.Callable:
                # Bug on Python < 3.9, https://bugs.python.org/issue42195
                return a
            a = a.copy_with(tuple([maybe_replace_reprs(arg) for arg in a.__args__]))
        return a

    return str(inspect.formatannotation(maybe_replace_reprs(annot)))


class Function(Doc):
    """
    Representation of documentation for a function or method.
    """
    __slots__ = ('cls',)

    def __init__(self, name: str, module: Module, obj, *, cls: Class = None):
        """
        Same as `pdoc.Doc`, except `obj` must be a
        Python function object. The docstring is gathered automatically.

        `cls` should be set when this is a method or a static function
        beloing to a class. `cls` should be a `pdoc.Class` object.

        `method` should be `True` when the function is a method. In
        all other cases, it should be `False`.
        """
        assert callable(obj), (name, module, obj)
        super().__init__(name, module, obj)

        self.cls = cls
        """
        The `pdoc.Class` documentation object if the function is a method.
        If not, this is None.
        """

    @property
    def is_method(self) -> bool:
        """
        Whether this function is a normal bound method.

        In particular, static and class methods have this set to False.
        """
        assert self.cls
        return not Class._method_type(self.cls.obj, self.name)

    @property
    def method(self):
        warn('`Function.method` is deprecated. Use: `Function.is_method`', DeprecationWarning,
             stacklevel=2)
        return self.is_method

    __pdoc__['Function.method'] = False

    def funcdef(self) -> str:
        """
        Generates the string of keywords used to define the function,
        for example `def` or `async def`.
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

    def return_annotation(self, *, link=None) -> str:
        """Formatted function return type annotation or empty string if none."""
        annot = ''
        for method in (
                lambda: _get_type_hints(self.obj)['return'],
                # Mainly for non-property variables
                lambda: _get_type_hints(cast(Class, self.cls).obj)[self.name],
                # global variables
                lambda: _get_type_hints(not self.cls and self.module.obj)[self.name],
                lambda: inspect.signature(self.obj).return_annotation,
                # Use raw annotation strings in unmatched forward declarations
                lambda: cast(Class, self.cls).obj.__annotations__[self.name],
                # Extract annotation from the docstring for C builtin function
                lambda: Function._signature_from_string(self).return_annotation,
        ):
            try:
                annot = method()
            except Exception:
                continue
            else:
                break
        else:
            # Don't warn on variables. The annotation just isn't available.
            if not isinstance(self, Variable):
                warn(f"Error handling return annotation for {self!r}", stacklevel=3)

        if annot is inspect.Parameter.empty or not annot:
            return ''

        if isinstance(annot, str):
            s = annot
        else:
            s = _formatannotation(annot)
            s = re.sub(r'\bForwardRef\((?P<quot>[\"\'])(?P<str>.*?)(?P=quot)\)',
                       r'\g<str>', s)
        s = s.replace(' ', '\N{NBSP}')  # Better line breaks in html signatures

        if link:
            from pdoc.html_helpers import _linkify
            s = re.sub(r'[\w\.]+', partial(_linkify, link=link, module=self.module), s)
        return s

    def params(self, *, annotate: bool = False, link: Callable[[Doc], str] = None) -> List[str]:
        """
        Returns a list where each element is a nicely formatted
        parameter of this function. This includes argument lists,
        keyword arguments and default values, and it doesn't include any
        optional arguments whose names begin with an underscore.

        If `annotate` is True, the parameter strings include [PEP 484]
        type hint annotations.

        [PEP 484]: https://www.python.org/dev/peps/pep-0484/
        """
        return self._params(self, annotate=annotate, link=link, module=self.module)

    @staticmethod
    def _params(doc_obj, annotate=False, link=None, module=None):
        try:
            # We want __init__ to actually be implemented somewhere in the
            # MRO to still satisfy https://github.com/pdoc3/pdoc/issues/124
            if (
                inspect.isclass(doc_obj.obj)
                and doc_obj.obj.__init__ is not object.__init__
            ):
                # Remove the first argument (self) from __init__ signature
                init_sig = inspect.signature(doc_obj.obj.__init__)
                init_params = list(init_sig.parameters.values())
                signature = init_sig.replace(parameters=init_params[1:])
            else:
                signature = inspect.signature(doc_obj.obj)
        except ValueError:
            signature = Function._signature_from_string(doc_obj)
            if not signature:
                return ['...']

        def safe_default_value(p: inspect.Parameter):
            value = p.default
            if value is inspect.Parameter.empty:
                return p

            replacement = next((i for i in ('os.environ',
                                            'sys.stdin',
                                            'sys.stdout',
                                            'sys.stderr',)
                                if value is eval(i)), None)
            if not replacement:
                if isinstance(value, enum.Enum):
                    replacement = str(value)
                elif inspect.isclass(value):
                    replacement = f'{value.__module__ or _UNKNOWN_MODULE}.{value.__qualname__}'
                elif ' at 0x' in repr(value):
                    replacement = re.sub(r' at 0x\w+', '', repr(value))

                nonlocal link
                if link and ('<' in repr(value) or '>' in repr(value)):
                    import html
                    replacement = html.escape(replacement or repr(value))

            if replacement:
                class mock:
                    def __repr__(self):
                        return replacement
                return p.replace(default=mock())
            return p

        params = []
        kw_only = False
        pos_only = False
        EMPTY = inspect.Parameter.empty

        if link:
            from pdoc.html_helpers import _linkify
            _linkify = partial(_linkify, link=link, module=module)

        for p in signature.parameters.values():  # type: inspect.Parameter
            if not _is_public(p.name) and p.default is not EMPTY:
                continue

            if p.kind == p.POSITIONAL_ONLY:
                pos_only = True
            elif pos_only:
                params.append("/")
                pos_only = False

            if p.kind == p.VAR_POSITIONAL:
                kw_only = True
            if p.kind == p.KEYWORD_ONLY and not kw_only:
                kw_only = True
                params.append('*')

            p = safe_default_value(p)

            if not annotate:
                p = p.replace(annotation=EMPTY)

            formatted = p.name
            if p.annotation is not EMPTY:
                annotation = _formatannotation(p.annotation).replace(' ', '\N{NBSP}')
                # "Eval" forward-declarations (typing string literals)
                if isinstance(p.annotation, str):
                    annotation = annotation.strip("'")
                if link:
                    annotation = re.sub(r'[\w\.]+', _linkify, annotation)
                formatted += f':\N{NBSP}{annotation}'
            if p.default is not EMPTY:
                if p.annotation is not EMPTY:
                    formatted += f'\N{NBSP}=\N{NBSP}{repr(p.default)}'
                else:
                    formatted += f'={repr(p.default)}'
            if p.kind == p.VAR_POSITIONAL:
                formatted = f'*{formatted}'
            elif p.kind == p.VAR_KEYWORD:
                formatted = f'**{formatted}'

            params.append(formatted)

        if pos_only:
            params.append("/")

        return params

    @staticmethod
    @lru_cache()
    def _signature_from_string(self):
        signature = None
        for expr, cleanup_docstring, filter in (
                # Full proper typed signature, such as one from pybind11
                (r'^{}\(.*\)(?: -> .*)?$', True, lambda s: s),
                # Human-readable, usage-like signature from some Python builtins
                # (e.g. `range` or `slice` or `itertools.repeat` or `numpy.arange`)
                (r'^{}\(.*\)(?= -|$)', False, lambda s: s.replace('[', '').replace(']', '')),
        ):
            strings = sorted(re.findall(expr.format(self.name),
                                        self.docstring, re.MULTILINE),
                             key=len, reverse=True)
            if strings:
                string = filter(strings[0])
                _locals, _globals = {}, {}
                _globals.update({'capsule': None})  # pybind11 capsule data type
                _globals.update(typing.__dict__)
                _globals.update(self.module.obj.__dict__)
                # Trim binding module basename from type annotations
                # See: https://github.com/pdoc3/pdoc/pull/148#discussion_r407114141
                module_basename = self.module.name.rsplit('.', maxsplit=1)[-1]
                if module_basename in string and module_basename not in _globals:
                    string = re.sub(fr'(?<!\.)\b{module_basename}\.\b', '', string)

                try:
                    exec(f'def {string}: pass', _globals, _locals)
                except SyntaxError:
                    continue
                signature = inspect.signature(_locals[self.name])
                if cleanup_docstring and len(strings) == 1:
                    # Remove signature from docstring variable
                    self.docstring = self.docstring.replace(strings[0], '')
                break
        return signature

    @property
    def refname(self) -> str:
        return f'{self.cls.refname if self.cls else self.module.refname}.{self.name}'


class Variable(Doc):
    """
    Representation of a variable's documentation. This includes
    module, class, and instance variables.
    """
    __slots__ = ('cls', 'instance_var')

    def __init__(self, name: str, module: Module, docstring, *,
                 obj=None, cls: Class = None, instance_var: bool = False):
        """
        Same as `pdoc.Doc`, except `cls` should be provided
        as a `pdoc.Class` object when this is a class or instance
        variable.
        """
        super().__init__(name, module, obj, docstring)

        self.cls = cls
        """
        The `pdoc.Class` object if this is a class or instance
        variable. If not (i.e. it is a global variable), this is None.
        """

        self.instance_var = instance_var
        """
        True if variable is some class' instance variable (as
        opposed to class variable).
        """

    @property
    def qualname(self) -> str:
        if self.cls:
            return f'{self.cls.qualname}.{self.name}'
        return self.name

    @property
    def refname(self) -> str:
        return f'{self.cls.refname if self.cls else self.module.refname}.{self.name}'

    def type_annotation(self, *, link=None) -> str:
        """Formatted variable type annotation or empty string if none."""
        return Function.return_annotation(cast(Function, self), link=link)


class External(Doc):
    """
    A representation of an external identifier. The textual
    representation is the same as an internal identifier.

    External identifiers are also used to represent something that is
    not documented but appears somewhere in the public interface (like
    the ancestor list of a class).
    """

    __pdoc__["External.docstring"] = """
        An empty string. External identifiers do not have
        docstrings.
        """
    __pdoc__["External.module"] = """
        Always `None`. External identifiers have no associated
        `pdoc.Module`.
        """
    __pdoc__["External.name"] = """
        Always equivalent to `pdoc.External.refname` since external
        identifiers are always expressed in their fully qualified
        form.
        """

    def __init__(self, name: str):
        """
        Initializes an external identifier with `name`, where `name`
        should be a fully qualified name.
        """
        super().__init__(name, None, None)

    def url(self, *args, **kwargs):
        """
        `External` objects return absolute urls matching `/{name}.ext`.
        """
        return f'/{self.name}.ext'
