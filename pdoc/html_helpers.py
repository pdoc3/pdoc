"""
Helper functions for HTML output.
"""
import re
from functools import partial
from warnings import warn

import markdown

import pdoc


def minify_css(css,
               _whitespace=partial(re.compile(r'\s*([,{:;}])\s*').sub, r'\1'),
               _comments=partial(re.compile(r'/\*.*?\*/', flags=re.DOTALL).sub, ''),
               _trailing_semicolon=partial(re.compile(r';\s*}').sub, '}')):
    """
    Minify CSS by removing extraneous whitespace, comments, and trailing semicolons.
    """
    return _trailing_semicolon(_whitespace(_comments(css))).strip()


def minify_html(html,
                _minify=partial(
                    re.compile(r'(.*?)(<pre\b.*?</pre\b\s*>)|(.*)', re.IGNORECASE | re.DOTALL).sub,
                    lambda m, _norm_space=partial(re.compile(r'\s\s+').sub, '\n'): (
                        _norm_space(m.group(1) or '') +
                        (m.group(2) or '') +
                        _norm_space(m.group(3) or '')
                    ))
                ):
    """
    Minify HTML by replacing all consecutive whitespace with a single space
    (or newline) character, except inside `<pre>` tags.
    """
    return _minify(html)


def glimpse(text, max_length=153, *, paragraph=True,
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


def to_html(text, docformat='markdown', *,
            module: pdoc.Module = None, link=None,
            # Matches markdown code spans not +directly+ within links.
            # E.g. `code` and [foo is `bar`]() but not [`code`](...)
            # Also skips \-escaped grave quotes.
            _code_refs=re.compile(r'(?<![\[\\])`(?!\])([^`]|(?<=\\)`)+`').sub):
    """
    Returns HTML of `text` interpreted as `docformat`.

    `module` should be the documented module (so the references can be
    resolved) and `link` is the hyperlinking function like the one in the
    example template.
    """
    assert docformat in ('markdown', 'md'), docformat  # TODO: Add support for NumpyDoc / Google

    if module and link:

        def linkify(match, _is_pyident=re.compile(r'^[a-zA-Z_]\w*(\.\w+)+$').match):
            nonlocal link, module
            matched = match.group(0)
            refname = matched[1:-1]
            refname = refname.rstrip('()')  # Function specified with parentheses
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


def extract_toc(text):
    """
    Returns HTML Table of Contents containing markdown titles in `text`.
    """
    toc, _ = _md.reset().convert('[TOC]\n\n@CUT@\n\n' + text).split('@CUT@', 1)
    if toc.endswith('<p>'):  # CUT was put into its own paragraph
        toc = toc[:-3].rstrip()
    return toc
