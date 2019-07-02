`pdoc` extracts documentation of:

* modules (including submodules),
* functions (including methods, properties, coroutines ...),
* classes, and
* variables (including globals, class variables, and instance variables).

Documentation is extracted from live objects' [docstrings]
using Python's `__doc__` attribute[^execution]. Documentation for
variables is found by examining objects' abstract syntax trees.

[docstrings]: https://docs.python.org/3/glossary.html#term-docstring

[^execution]:
    Documented modules are executed in order to provide `__doc__`
    attributes. Any non-fenced global code in imported modules will
    affect the current environment.


What objects are documented?
----------------------------
`pdoc` only extracts _public API_ documentation.[^public]
All objects (modules, functions, classes, variables) are only
considered public if their _identifiers don't begin with an
underscore_ ( \_ ).[^private]

[^public]:
    Here, public API refers to the API that is made available
    to your project end-users, not the public API e.g. of a
    private class that can be reasonably extended elsewhere
    by your project developers.

[^private]:
    Prefixing private, implementation-specific objects with
    an underscore is [a common convention].

[a common convention]: https://docs.python.org/3/tutorial/classes.html#private-variables

In addition, if a module defines [`__all__`][__all__], then only
the identifiers contained in this list will be considered public.
Otherwise, a module's global identifiers are considered public
only if they don't begin with an underscore and are defined
in this exact module (i.e. not imported from somewhere else).

[__all__]: https://docs.python.org/3/tutorial/modules.html#importing-from-a-package

By transitivity, sub-objects of non-public objects
(e.g. submodules of non-public modules, methods of non-public classes etc.)
are not public and thus not documented.


Where does `pdoc` get documentation from?
-----------------------------------------
In Python, objects like modules, functions, classes, and methods
have a special attribute `__doc__` which contains that object's
documentation string ([docstring][docstrings]).
For example, the following code defines a function with a docstring
and shows how to access its contents:

    >>> def test():
    ...     """This is a docstring."""
    ...     pass
    ...
    >>> test.__doc__
    'This is a docstring.'

It's pretty much the same with classes and modules.
See [PEP-257] for Python docstring conventions.

[PEP-257]: https://www.python.org/dev/peps/pep-0257/

These docstrings are set as descriptions for each module, class,
function, and method listed in the documentation produced by `pdoc`.

`pdoc` extends the standard use of docstrings in Python in two
important ways: by allowing methods to inherit docstrings, and
by introducing syntax for docstrings for variables.


### Docstrings inheritance

`pdoc` considers methods' docstrings inherited from superclass methods',
following the normal class inheritance patterns.
Consider the following code example:

    >>> class A:
    ...     def test(self):
    ...         """Docstring for A."""
    ...         pass
    ...
    >>> class B(A):
    ...     def test(self):
    ...         pass
    ...
    >>> A.test.__doc__
    'Docstring for A.'
    >>> B.test.__doc__
    None

In Python, the docstring for `B.test` doesn't exist, even though a
docstring was defined for `A.test`.
When `pdoc` generates documentation for the code such as above,
it will automatically attach the docstring for `A.test` to
`B.test` if `B.test` does not define its own docstring.
In the default HTML template, such inherited docstrings are greyed out.


### Docstrings for variables

Python by itself [doesn't allow docstrings attached to variables][PEP-224].
However, `pdoc` supports docstrings attached to module (or global)
variables, class variables, and object instance variables; all in
the same way as proposed in [PEP-224], with a docstring following the
variable assignment.
For example:

[PEP-224]: http://www.python.org/dev/peps/pep-0224

    module_variable = 1
    """Docstring for module_variable."""

    class C:
        class_variable = 2
        """Docstring for class_variable."""

        def __init__(self):
            self.variable = 3
            """Docstring for instance variable."""

While the resulting variables have no `__doc__` attribute,
`pdoc` compensates by reading the source code (when available)
and parsing the syntax tree.

By convention, variables defined in a class' `__init__` method
and attached to `self` are considered and documented as
instance variables.

Class and instance variables can also [inherit docstrings].

[inherit docstrings]: #docstrings-inheritance


Overriding docstrings with `__pdoc__`
-------------------------------------
Docstrings for objects can be disabled or overridden with a special
module-level dictionary `__pdoc__`. The _keys_
should be string identifiers within the scope of the module or,
alternatively, fully-qualified reference names. E.g. for instance
variable `self.variable` of class `C`, its module-level identifier is
`'C.variable'`.

If `__pdoc__[key] = False`, then `key` (and its members) will be
**excluded from the documentation** of the module.

Alternatively, the _values_ of `__pdoc__` should be the overriding docstrings.
This particular feature is useful when there's no feasible way of
attaching a docstring to something. A good example of this is a
[namedtuple](https://docs.python.org/3/library/collections.html#collections.namedtuple):

    __pdoc__ = {}

    Table = namedtuple('Table', ['types', 'names', 'rows'])
    __pdoc__['Table.types'] = 'Types for each column in the table.'
    __pdoc__['Table.names'] = 'The names of each column in the table.'
    __pdoc__['Table.rows'] = 'Lists corresponding to each row in the table.'

`pdoc` will then show `Table` as a class with documentation for the
`types`, `names` and `rows` members.

.. note::
    The assignments to `__pdoc__` need to be placed where they'll be
    executed when the module is imported. For example, at the top level
    of a module or in the definition of a class.


Supported docstring formats
---------------------------
Currently, pure Markdown (with [extensions]), [numpydoc],
and [Google-style] docstrings formats are supported,
along with some [reST directives].

Additionally, if `latex_math` [template config] option is enabled,
LaTeX math syntax is supported when placed between
[recognized delimiters]: `\(...\)` for inline equations and
`\[...\]` or `$$...$$` for block equations. Note, you need to escape
your backslashes in Python docstrings (`\\(`, `\\frac{}{}`, ...)
or, alternatively, use [raw string literals].

*[reST]: reStructuredText
[extensions]: https://python-markdown.github.io/extensions/#officially-supported-extensions
[numpydoc]: https://numpydoc.readthedocs.io/
[Google-style]: http://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings
[reST directives]: #supported-rest-directives
[template config]: #custom-templates
[recognized delimiters]: http://docs.mathjax.org/en/latest/tex.html#tex-and-latex-math-delimiters
[raw string literals]: https://www.journaldev.com/23598/python-raw-string


### Supported reST directives

The following reST directives should work:

* specific and generic [admonitions],
* [`.. image::`][image] or `.. figure::` (without options),
* [`.. include::`][include], with support for the options:
  `:start-line:`, `:end-line:`, `:start-after:` and `:end-before:`.
* [`.. math::`][math]
* `.. versionadded::`
* `.. versionchanged::`
* `.. deprecated::`
* `.. todo::`

[admonitions]: http://docutils.sourceforge.net/docs/ref/rst/directives.html#admonitions
[image]: http://docutils.sourceforge.net/docs/ref/rst/directives.html#images
[include]: http://docutils.sourceforge.net/docs/ref/rst/directives.html#including-an-external-document-fragment
[math]: http://docutils.sourceforge.net/docs/ref/rst/directives.html#math


Linking to other identifiers
----------------------------
In your documentation, you may refer to other identifiers in
your modules. When exporting to HTML, linking is automatically
done whenever you surround an identifier with [backticks] ( \` ).
The identifier name must be fully qualified, for example
<code>\`pdoc.Doc.docstring\`</code> is correct (and will link to
`pdoc.Doc.docstring`) while <code>\`Doc.docstring\`</code> is _not_.

[backticks]: https://en.wikipedia.org/wiki/Grave_accent#Use_in_programming


Command-line interface
----------------------
[cmd]: #command-line-interface
`pdoc` includes a feature-rich "binary" program for producing
HTML and plain text documentation of your modules.
For example, to produce HTML documentation of your whole package
in subdirectory 'build' of the current directory, using the default
HTML template, run:

    $ pdoc --html --output-dir build my_package

To run a local HTTP server while developing your package or writing
docstrings for it, run:

    $ pdoc --http : my_package

To re-build documentation as part of your continuous integration (CI)
best practice, i.e. ensuring all reference links are correct and
up-to-date, make warnings error loudly by settings the environment
variable [`PYTHONWARNINGS`][PYTHONWARNINGS] before running pdoc:

    $ export PYTHONWARNINGS='error::UserWarning'

[PYTHONWARNINGS]: https://docs.python.org/3/using/cmdline.html#envvar-PYTHONWARNINGS

For brief usage instructions, type:

    $ pdoc --help


Programmatic usage
------------------
The main entry point is `pdoc.Module` which wraps a module object
and recursively imports and wraps any submodules and their members.

After all related modules are wrapped (related modules are those that
share the same `pdoc.Context`), you need to call
`pdoc.link_inheritance` with the used `Context` instance to
establish class inheritance links.

Afterwards, you can use `pdoc.Module.html` and `pdoc.Module.text`
methods to output documentation in the desired format.
For example:

    import pdoc

    modules = ['a', 'b']  # Public submodules are auto-imported
    context = pdoc.Context()

    modules = [pdoc.Module(mod, context=context)
               for mod in modules]
    pdoc.link_inheritance(context)

    def recursive_htmls(mod):
        yield mod.name, mod.html()
        for submod in mod.submodules():
            yield from recursive_htmls(submod)

    for mod in modules:
        for module_name, html in recursive_htmls(mod):
            ...  # Process

When documenting a single module, you might find
functions `pdoc.html` and `pdoc.text` handy.
For importing arbitrary modules/files, use `pdoc.import_module`.

Alternatively, use the [runnable script][cmd] included with this package.


Custom templates
----------------
To override the built-in HTML/CSS and plain text templates, copy
the relevant templates from `pdoc/templates` directory into a directory
of your choosing and edit them. When you run [pdoc command][cmd]
afterwards, pass the directory path as a parameter to the
`--template-dir` switch.

.. tip::
    If you find you only need to apply minor alterations to the HTML template,
    see if you can do so by overriding just some of the following, placeholder
    sub-templates:

    * [_config.mako_]: Basic template configuration, affects the way templates
      are rendered.
    * _head.mako_: Included just before `</head>`. Best for adding resources and styles.
    * _logo.mako_: Included at the very top of the navigation sidebar. Empty by default.
    * _credits.mako_: Included in the footer, right before pdoc version string.

    See [default template files] for reference.

.. tip::
   You can also alter individual [_config.mako_] preferences using the
   `--config` command-line switch.

If working with `pdoc` programmatically, _prepend_ the directory with
modified templates into the `directories` list of the
`pdoc.tpl_lookup` object.

[_config.mako_]: https://github.com/pdoc3/pdoc/blob/master/pdoc/templates/config.mako
[default template files]: https://github.com/pdoc3/pdoc/tree/master/pdoc/templates


Compatibility
-------------
`pdoc` requires Python 3.5+.
The last version to support Python 2.x is [pdoc3 0.3.x].

[pdoc3 0.3.x]: https://pypi.org/project/pdoc3/0.3.11/


Contributing
------------
`pdoc` is [on GitHub]. Bug reports and pull requests are welcome.

[on GitHub]: https://github.com/pdoc3/pdoc


License
-------
`pdoc` is licensed under the terms of GNU [AGPL-3.0]{: rel=license} or later,
meaning you can use it for any reasonable purpose and remain in
complete ownership of all the documentation you produce,
but you are also encouraged to make sure any upgrades to `pdoc`
itself find their way back to the community.

[AGPL-3.0]: https://www.gnu.org/licenses/agpl-3.0.html
