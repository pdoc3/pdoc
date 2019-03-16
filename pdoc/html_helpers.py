"""
Helper functions for HTML output.
"""
import inspect
import os.path
import re
from functools import partial, lru_cache
from typing import Callable
from warnings import warn

import markdown

import pdoc


@lru_cache()
def minify_css(css: str,
               _whitespace=partial(re.compile(r'\s*([,{:;}])\s*').sub, r'\1'),
               _comments=partial(re.compile(r'/\*.*?\*/', flags=re.DOTALL).sub, ''),
               _trailing_semicolon=partial(re.compile(r';\s*}').sub, '}')):
    """
    Minify CSS by removing extraneous whitespace, comments, and trailing semicolons.
    """
    return _trailing_semicolon(_whitespace(_comments(css))).strip()


def minify_html(html: str,
                _minify=partial(
                    re.compile(r'(.*?)(<pre\b.*?</pre\b\s*>)|(.*)', re.IGNORECASE | re.DOTALL).sub,
                    lambda m, _norm_space=partial(re.compile(r'\s\s+').sub, '\n'): (
                        _norm_space(m.group(1) or '') +
                        (m.group(2) or '') +
                        _norm_space(m.group(3) or '')))):
    """
    Minify HTML by replacing all consecutive whitespace with a single space
    (or newline) character, except inside `<pre>` tags.
    """
    return _minify(html)


def glimpse(text: str, max_length=153, *, paragraph=True,
            _split_paragraph=partial(re.compile(r'\s*\n\s*\n\s*').split, maxsplit=1),
            _trim_last_word=partial(re.compile(r'\S+$').sub, ''),
            _remove_titles=partial(re.compile(r'^(#+|-{4,}|={4,})', re.MULTILINE).sub, ' ')):
    """
    Returns a short excerpt (e.g. first paragraph) of text.
    If `paragraph` is True, the first paragraph will be returned,
    but never longer than `max_length` characters.
    """
    text = text.lstrip()
    if paragraph:
        text, *rest = _split_paragraph(text)
        if rest:
            text = text.rstrip('.')
            text += ' …'
        text = _remove_titles(text).strip()

    if len(text) > max_length:
        text = _trim_last_word(text[:max_length - 2])
        if not text.endswith('.') or not paragraph:
            text = text.rstrip('. ') + ' …'
    return text


_md = markdown.Markdown(
    output_format='html5',
    extensions=[
        "markdown.extensions.abbr",
        "markdown.extensions.attr_list",
        "markdown.extensions.def_list",
        "markdown.extensions.fenced_code",
        "markdown.extensions.footnotes",
        "markdown.extensions.tables",
        "markdown.extensions.admonition",
        "markdown.extensions.smarty",
        "markdown.extensions.toc",
    ],
    extension_configs={
        "markdown.extensions.smarty": dict(
            smart_dashes=True,
            smart_ellipses=True,
            smart_quotes=False,
            smart_angled_quotes=False,
        ),
    },
)


class ReferenceWarning(UserWarning):
    """
    This warning is raised in `to_html` when a object reference in markdown
    doesn't match any documented objects.

    Look for this warning to catch typos / references to obsolete symbols.
    """


class _ToMarkdown:
    """
    This class serves as a namespace for methods converting common
    documentation formats into markdown our Python-Markdown with
    addons can ingest.

    If debugging regexs (I can't imagine why that would be necessary
    — they are all perfect!) an insta-preview tool such as RegEx101.com
    will come in handy.
    """
    @staticmethod
    def _deflist(name, type, desc,
                 # Wraps any identifiers and string literals in parameter type spec
                 # in backticks while skipping common "stopwords" such as 'or', 'of',
                 # 'optional' ... See §4 Parameters:
                 # https://numpydoc.readthedocs.io/en/latest/format.html#sections
                 _type_parts=partial(
                     re.compile(r'[\w.\'"]+').sub,
                     lambda m: ('{}' if m.group(0) in ('of', 'or', 'default', 'optional') else
                                '`{}`').format(m.group(0)))):
        """
        Returns `name`, `type`, and `desc` formatted as a
        Python-Markdown definition list entry. See also:
        https://python-markdown.github.io/extensions/definition_lists/
        """
        type = _type_parts(type or '')
        desc = desc or '&nbsp;'
        assert _ToMarkdown._is_indented_4_spaces(desc)
        if type:
            return '**`{}`** :&ensp;{}\n:   {}\n\n'.format(name, type, desc)
        return '**`{}`**\n:   {}\n\n'.format(name, desc)

    @staticmethod
    def _numpy_params(match,
                      _name_parts=partial(re.compile(', ').sub, '`**, **`')):
        """ Converts NumpyDoc parameter (etc.) sections into Markdown. """
        name, type, desc = match.groups()
        desc = desc.strip()
        if name and (type or desc):
            name = _name_parts(name)
            return _ToMarkdown._deflist(name, type, desc)
        return match.group(0)

    @staticmethod
    def _numpy_seealso(match):
        """
        Converts NumpyDoc "See Also" section either into referenced code,
        optionally within a definition list.
        """
        title, spec_with_desc, simple_list = match.groups()
        if spec_with_desc:
            return title + '\n\n'.join('`{}`\n:   {}'.format(*map(str.strip, line.split(':', 1)))
                                       for line in filter(None, spec_with_desc.split('\n')))
        return title + ', '.join('`{}`'.format(i) for i in simple_list.split(', '))

    @staticmethod
    def numpy(text,
              # All kinds of numpydoc Parameters (optionally with types; descriptions)
              _params=partial(
                  re.compile(r'^([\w*]+(?:, [\w*]+)*)(?: ?: (.*)(?<!\.)$)?'
                             r'((?:\n(?: {4}.*|$))*)', re.MULTILINE).sub,
                  _numpy_params.__func__),
              _seealso=partial(
                  re.compile(r'(See Also\n-{8}\n)(?:((?:\n?[\w.]* ?: .*)+)|(.*))').sub,
                  _numpy_seealso.__func__)):
        """
        Convert `text` in numpydoc docstring format to Markdown
        to be further converted later.
        """
        text = _seealso(text)
        text = _params(text)
        return text

    @staticmethod
    def _is_indented_4_spaces(txt, _3_spaces_or_less=re.compile(r'\n\s{0,3}\S').search):
        return '\n' not in txt or not _3_spaces_or_less(txt)

    @staticmethod
    def _fix_indent(name, type, desc):
        """Mazbe fix indent from 2 to 4 spaces."""
        if not _ToMarkdown._is_indented_4_spaces(desc):
            desc = desc.replace('\n', '\n  ')
        return name, type, desc

    @staticmethod
    def google(text,
               _googledoc_sections=partial(
                   re.compile(r'^([A-Z]\w+):$\n((?:\n?(?: {2,}.*|$))+)', re.MULTILINE).sub,
                   lambda m, _params=partial(
                           re.compile(r'^([\w*]+)(?: \(([\w.,=\[\] ]+)\))?: '
                                      r'((?:.*)(?:\n(?: {2,}.*|$))*)', re.MULTILINE).sub,
                           lambda m: _ToMarkdown._deflist(*_ToMarkdown._fix_indent(*m.groups()))): (
                       m.group() if not m.group(2) else '\n{}\n-----\n{}'.format(
                           m.group(1), _params(inspect.cleandoc('\n' + m.group(2))))))):
        """
        Convert `text` in Google-style docstring format to Markdown
        to be further converted later.
        """
        return _googledoc_sections(text)

    @staticmethod
    def _admonition(match, module=None):
        indent, type, value, text = match.groups()

        if type == 'include' and module:
            try:
                return _ToMarkdown._include_file(indent, value,
                                                 _ToMarkdown._directive_opts(text), module)
            except Exception as e:
                raise RuntimeError('`.. include:: {}` error in module {!r}: {}'
                                   .format(value, module.name, e))
        if type in ('image', 'figure'):
            return '{}![{}]({})\n'.format(
                indent, text.translate(str.maketrans({'\n': ' ',
                                                      '[': '\\[',
                                                      ']': '\\]'})).strip(), value)
        if type == 'versionchanged':
            title = 'Changed in version:&ensp;' + value
        elif type == 'versionadded':
            title = 'Added in version:&ensp;' + value
        elif type == 'deprecated' and value:
            title = 'Deprecated since version:&ensp;' + value
        elif type == 'admonition':
            title = value
        elif type.lower() == 'todo':
            title = 'TODO'
            text = value + ' ' + text
        else:
            title = type.capitalize()
            if value:
                title += ':&ensp;' + value

        text = '\n'.join(indent + '    ' + line
                         for line in inspect.cleandoc(text).split('\n'))
        return '{}!!! {} "{}"\n{}\n'.format(indent, type, title, text)

    @staticmethod
    def admonitions(text, module):
        """
        Process reStructuredText's block directives such as
        `.. warning::`, `.. deprecated::`, `.. versionadded::`, etc.
        and turn them into Python-M>arkdown admonitions.

        See: https://python-markdown.github.io/extensions/admonition/
        """
        substitute = partial(re.compile(r'^(?P<indent> *)\.\. ?(\w+)::(?: *(.*))?'
                                        r'((?:\n(?:(?P=indent) +.*| *$))*)', re.MULTILINE).sub,
                             partial(_ToMarkdown._admonition, module=module))
        # Apply twice for nested (e.g. image inside warning)
        return substitute(substitute(text))

    @staticmethod
    def _include_file(indent: str, path: str, options: dict, module: pdoc.Module) -> str:
        start_line = int(options.get('start-line', 0))
        end_line = int(options.get('end-line', 0)) or None
        start_after = options.get('start-after')
        end_before = options.get('end-before')

        with open(os.path.join(os.path.dirname(module.obj.__file__), path),
                  encoding='utf-8') as f:
            text = ''.join(list(f)[start_line:end_line])

        if start_after:
            text = text[text.index(start_after) + len(start_after):]
        if end_before:
            text = text[:text.index(end_before)]

        text = re.sub(r'\n', '\n' + indent, indent + text.rstrip())
        return text

    @staticmethod
    def _directive_opts(text: str) -> dict:
        return dict(re.findall(r'^ *:([^:]+): *(.*)', text, re.MULTILINE))

    @staticmethod
    def doctests(text,
                 _indent_doctests=partial(
                     re.compile(r'(?:^(?P<fence>```|~~~).*\n)?'
                                r'(?:^>>>.*'
                                r'(?:\n(?:(?:>>>|\.\.\.).*))*'
                                r'(?:\n.*)?\n\n?)+'
                                r'(?P=fence)?', re.MULTILINE).sub,
                     lambda m: (m.group(0) if m.group('fence') else
                                ('\n    ' + '\n    '.join(m.group(0).split('\n')) + '\n\n')))):
        """
        Indent non-fenced (`~~~`) top-level (0-indented)
        doctest blocks so they render as code.
        """
        return _indent_doctests(text)

    @staticmethod
    def raw_urls(text):
        """Wrap URLs in Python-Markdown-compatible <angle brackets>."""
        return re.sub(r'(?<!<)(\s*)((?:http|ftp)s?://[^>)\s]+)(\s*)(?!>)', r'\1<\2>\3', text)


def to_html(text: str, docformat: str = 'numpy,google', *,
            module: pdoc.Module = None, link: Callable[..., str] = None,
            # Matches markdown code spans not +directly+ within links.
            # E.g. `code` and [foo is `bar`]() but not [`code`](...)
            # Also skips \-escaped grave quotes.
            _code_refs=re.compile(r'(?<![\[\\])`(?!])(?:[^`]|(?<=\\)`)+`').sub):
    """
    Returns HTML of `text` interpreted as `docformat`.
    By default, Numpydoc and Google-style docstrings are assumed,
    as well as pure Markdown.

    `module` should be the documented module (so the references can be
    resolved) and `link` is the hyperlinking function like the one in the
    example template.
    """
    assert all(i in (None, '', 'numpy', 'google') for i in docformat.split(',')), docformat

    text = _ToMarkdown.admonitions(text, module)
    text = _ToMarkdown.raw_urls(text)

    if 'google' in docformat:
        text = _ToMarkdown.google(text)

    # If doing both, do numpy after google, otherwise google-style's
    # headings are incorrectly interpreted as numpy params
    if 'numpy' in docformat:
        text = _ToMarkdown.numpy(text)

    text = _ToMarkdown.doctests(text)

    if module and link:

        def linkify(match, _is_pyident=re.compile(r'^[a-zA-Z_]\w*(\.\w+)+$').match):
            nonlocal link, module
            matched = match.group(0)
            refname = matched[1:-1]
            dobj = module.find_ident(refname)
            if isinstance(dobj, pdoc.External):
                if not _is_pyident(refname):
                    return matched
                # If refname in documentation has a typo or is obsolete, warn.
                # XXX: Assume at least the first part of refname, i.e. the package, is correct.
                module_part = module.find_ident(refname.split('.')[0])
                if not isinstance(module_part, pdoc.External):
                    warn('Code reference `{}` in module "{}" does not match any '
                         'documented object.'.format(refname, module.refname),
                         ReferenceWarning, stacklevel=3)
            return link(dobj, fmt='`{}`')

        text = _code_refs(linkify, text)

    return _md.reset().convert(text)


def extract_toc(text: str):
    """
    Returns HTML Table of Contents containing markdown titles in `text`.
    """
    toc, _ = _md.reset().convert('[TOC]\n\n@CUT@\n\n' + text).split('@CUT@', 1)
    if toc.endswith('<p>'):  # CUT was put into its own paragraph
        toc = toc[:-3].rstrip()
    return toc
