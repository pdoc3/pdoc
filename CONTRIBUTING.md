Contributing guidelines
=======================

Issues
------
**Only report issues for _pdoc3_ package on PyPI.**
If your issue pertains to older _pdoc_ package (on PyPI),
report the issue [here] or ... just stop using it.

[here]: https://github.com/mitmproxy/pdoc

Before reporting an issue, see if a similar issue is already open.
Also check if a similar issue was recently closed — your bug might
have been fixed already.

To have your issue dealt with promptly, it's best to construct a
[minimal working example] that exposes the issue in a clear and
reproducible manner.

[minimal working example]: https://en.wikipedia.org/wiki/Minimal_working_example


Installation
------------
To install a developmental version of the project,
first [fork the project]. Then:

    git clone git@github.com:YOUR_USERNAME/pdoc
    cd pdoc
    pip3 install -e .   # Mind the dot

[fork the project]: https://help.github.com/articles/fork-a-repo/


Testing
-------
Please write reasonable unit tests for any new / changed functionality.
See _pdoc/test_ directory for existing tests.
Before submitting a PR, ensure the tests pass:

    python setup.py test

Also ensure that idiomatic code style is respected by running:

    flake8 --max-line-length 100  


Documentation
-------------
See _doc/README.md_. All documentation is generated from
[pdoc]-compatible docstrings in code.

[pdoc]: https://pdoc3.github.io/pdoc


Pull requests
-------------
If you're new to proposing changes on GitHub, help yourself to an
[appropriate guide]. Additionally, please use explicit commit messages.
See [NumPy's development workflow] for inspiration.

[appropriate guide]: https://gist.github.com/Chaser324/ce0505fbed06b947d962
[NumPy's development workflow]: https://numpy.org/doc/stable/dev/development_workflow.html
