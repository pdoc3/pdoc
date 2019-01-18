[![](https://i.imgur.com/kQOtbBk.png)](https://pdoc3.github.io/pdoc/)

pdoc
====

[![Build Status](https://img.shields.io/travis/pdoc3/pdoc.svg?style=for-the-badge)](https://travis-ci.org/pdoc3/pdoc)
[![Code Coverage](https://img.shields.io/codecov/c/gh/pdoc3/pdoc.svg?style=for-the-badge)](https://codecov.io/gh/pdoc3/pdoc)
[![pdoc3 on PyPI](https://img.shields.io/pypi/v/pdoc3.svg?style=for-the-badge)](https://pypi.org/project/pdoc3)

Auto-generate API documentation for Python projects.

[**Project website**](https://pdoc3.github.io/pdoc/)

[Documentation]

[Documentation]: https://pdoc3.github.io/pdoc/doc/pdoc/


Installation
------------

    $ pip install pdoc3


Usage
-----
Pdoc will accept a Python module file, package directory or an import path.

    $ pdoc your_project

See `pdoc --help` for more command-line switches and the [documentation]
for more usage examples.


Features
--------
* Simple usage. Generate sensible API (+ prose) documentation without any
  special configuration.
* Support for common docstrings formats (Markdown, numpydoc, Google-style docstrings)
  and some reST directives.
* pdoc respects `__all__` when present.
* Inheritance used as applicable for inferring docstrings for class members.
* Support for documenting module, class, and instance variables by traversing ASTs.
* Automatic cross-linking of referenced identifiers in HTML.
* Overriding docstrings with special module-level `__pdoc__` dictionary.
* Built-in development web server for near instant preview of rendered docstrings.

The above features are explained in more detail in pdoc's [documentation]
(which was generated with pdoc).
