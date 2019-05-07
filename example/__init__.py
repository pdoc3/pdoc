"""
Welcome to pdoc!

This is an example module. Markdown in the docstring and included
files is rendered into html documentation.

.. include::readme.md

## admonitions
pdoc supports the following specially marked topics:

* attention
* caution
* danger
* error
* hint
* important
* note
* tip
* warning

These are known as
[admonitions](http://docutils.sourceforge.net/docs/ref/rst/directives.html#admonitions).

Here are some examples:

.. attention:: This is a attention admonition
.. caution:: This is a caution admonition
.. danger:: This is a danger admonition
.. error:: This is a error admonition
.. hint:: This is a hint admonition
.. important:: This is a important admonition
.. note:: This is a note admonition
.. tip:: This is a tip admonition
.. warning:: This is a warning admonition
.. admonition:: This is a generic admonition

.. tip:: You can include multiple lines as follows.
   This is the second line of the first paragraph.

   - The note contains all indented body elements
     following.
   - It includes this bullet list.

"""
import sys

MY_CONSTANT = 5


class Dog:
    def __init__(self, a):
        self.a = a

    def bark(self):
        print("ruff")


class Cat:
    def __init__(self, a):
        self.a = a

    def meow(self):
        print("meow")


def main() -> int:
    """This is the main function."""
    print("Hello world")


if __name__ == "__main__":
    sys.exit(main())
