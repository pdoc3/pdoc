[![](https://i.imgur.com/kQOtbBk.png)](https://pdoc3.github.io/pdoc/)

pdoc
====

[![Build Status](https://img.shields.io/travis/pdoc3/pdoc.svg?style=for-the-badge)](https://travis-ci.org/pdoc3/pdoc)
[![Code Coverage](https://img.shields.io/codecov/c/gh/pdoc3/pdoc.svg?style=for-the-badge)](https://codecov.io/gh/pdoc3/pdoc)
[![pdoc3 on PyPI](https://img.shields.io/pypi/v/pdoc3.svg?color=blue&style=for-the-badge)](https://pypi.org/project/pdoc3)

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
* Support for common [docstrings formats] (Markdown, numpydoc, Google-style docstrings),
  LaTeX math, and some [reST directives].
* Support for [PEP 484] and [PEP 526] type annotations.
* pdoc respects [`__all__`] when present.
* Docstrings for overridden class members are [inherited] if unspecified.
* Support for documenting module, class, and instance [_variables_] by traversing ASTs.
* Automatic [cross-linking] of referenced identifiers.
* Overriding docstrings generation with special module-level [`__pdoc__` dictionary].
* Easily extended and [customized templates].
* Built-in [development web server] for near-instant preview of rendered docstrings.

The above features are explained in more detail in pdoc's [documentation]
(generated with pdoc).

[docstrings formats]: https://pdoc3.github.io/pdoc/doc/pdoc/#supported-docstring-formats
[reST directives]: https://pdoc3.github.io/pdoc/doc/pdoc/#supported-rest-directives
[PEP 484]: https://www.python.org/dev/peps/pep-0484/
[PEP 526]: https://www.python.org/dev/peps/pep-0526/
[`__all__`]: https://pdoc3.github.io/pdoc/doc/pdoc/#what-objects-are-documented
[inherited]: https://pdoc3.github.io/pdoc/doc/pdoc/#docstrings-inheritance
[_variables_]: https://pdoc3.github.io/pdoc/doc/pdoc/#docstrings-for-variables
[cross-linking]: https://pdoc3.github.io/pdoc/doc/pdoc/#linking-to-other-identifiers
[`__pdoc__` dictionary]: https://pdoc3.github.io/pdoc/doc/pdoc/#overriding-docstrings-with-__pdoc__
[customized templates]: https://pdoc3.github.io/pdoc/doc/pdoc/#custom-templates
[development web server]: https://pdoc3.github.io/pdoc/doc/pdoc/#command-line-interface


Development
-----------
Check [CONTRIBUTING.md](CONTRIBUTING.md) for hacking details.
