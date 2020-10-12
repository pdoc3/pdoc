"""
Helper functions for HTML output.
"""
import inspect
import os
import re
import subprocess
import textwrap
import traceback
from contextlib import contextmanager
from functools import partial, lru_cache
from typing import Callable, Match
from warnings import warn
import xml.etree.ElementTree as etree

import markdown
from markdown.inlinepatterns import InlineProcessor
from markdown.util import AtomicString

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
    output_format='html5',    # type: ignore[arg-type]
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
            smart_dashes=True,          # type: ignore[dict-item]
            smart_ellipses=True,        # type: ignore[dict-item]
            smart_quotes=False,         # type: ignore[dict-item]
            smart_angled_quotes=False,  # type: ignore[dict-item]
        ),
    },
)


@contextmanager
def _fenced_code_blocks_hidden(text):
    def hide(text):
        def replace(match):
            orig = match.group()
            new = '@' + str(hash(orig)) + '@'
            hidden[new] = orig
            return new

        text = re.compile(r'^(?P<fence>```+|~~~+).*\n'
                          r'(?:.*\n)*?'
                          r'^(?P=fence)[ ]*(?!.)', re.MULTILINE).sub(replace, text)
        return text

    def unhide(text):
        for k, v in hidden.items():
            text = text.replace(k, v)
        return text

    hidden = {}
    # Via a manager object (a list) so modifications can pass back and forth as result[0]
    result = [hide(text)]
    yield result
    result[0] = unhide(result[0])


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
    def _deflist(name, type, desc):
        """
        Returns `name`, `type`, and `desc` formatted as a
        Python-Markdown definition list entry. See also:
        https://python-markdown.github.io/extensions/definition_lists/
        """
        # Wrap any identifiers and string literals in parameter type spec
        # in backticks while skipping common "stopwords" such as 'or', 'of',
        # 'optional' ... See §4 Parameters:
        # https://numpydoc.readthedocs.io/en/latest/format.html#sections
        type_parts = re.split(r'( *(?: of | or |, *default(?:=|\b)|, *optional\b) *)', type or '')
        type_parts[::2] = ['`{}`'.format(s) if s else s
                           for s in type_parts[::2]]
        type = ''.join(type_parts)

        desc = desc or '&nbsp;'
        assert _ToMarkdown._is_indented_4_spaces(desc)
        assert name or type
        ret = ""
        if name:
            # NOTE: Triple-backtick argument names so we skip linkifying them
            ret += '**```{}```**'.format(name.replace(', ', '```**, **```'))
        if type:
            ret += ' :&ensp;{}'.format(type) if ret else type
        ret += '\n:   {}\n\n'.format(desc)
        return ret

    @staticmethod
    def _numpy_params(match):
        """ Converts NumpyDoc parameter (etc.) sections into Markdown. """
        name, type, desc = match.group("name", "type", "desc")
        type = type or match.groupdict().get('just_type', None)
        desc = desc.strip()
        return _ToMarkdown._deflist(name, type, desc)

    @staticmethod
    def _numpy_seealso(match):
        """
        Converts NumpyDoc "See Also" section either into referenced code,
        optionally within a definition list.
        """
        spec_with_desc, simple_list = match.groups()
        if spec_with_desc:
            return '\n\n'.join('`{}`\n:   {}'.format(*map(str.strip, line.split(':', 1)))
                               for line in filter(None, spec_with_desc.split('\n')))
        return ', '.join('`{}`'.format(i) for i in simple_list.split(', '))

    @staticmethod
    def _numpy_sections(match):
        """
        Convert sections with parameter, return, and see also lists to Markdown
        lists.
        """
        section, body = match.groups()
        section = section.title()
        if section == 'See Also':
            body = re.sub(r'\n\s{4}\s*', ' ', body)  # Handle line continuation
            body = re.sub(r'^((?:\n?[\w.]* ?: .*)+)|(.*\w.*)',
                          _ToMarkdown._numpy_seealso, body)
        elif section in ('Returns', 'Yields', 'Raises', 'Warns'):
            body = re.sub(r'^(?:(?P<name>\*{0,2}\w+(?:, \*{0,2}\w+)*)'
                          r'(?: ?: (?P<type>.*))|'
                          r'(?P<just_type>\w[^\n`*]*))(?<!\.)$'
                          r'(?P<desc>(?:\n(?: {4}.*|$))*)',
                          _ToMarkdown._numpy_params, body, flags=re.MULTILINE)
        elif section in ('Parameters', 'Receives', 'Other Parameters',
                         'Arguments', 'Args', 'Attributes'):
            name = r'(?:\w|\{\w+(?:,\w+)+\})+'  # Support curly brace expansion
            body = re.sub(r'^(?P<name>\*{0,2}' + name + r'(?:, \*{0,2}' + name + r')*)'
                          r'(?: ?: (?P<type>.*))?(?<!\.)$'
                          r'(?P<desc>(?:\n(?: {4}.*|$))*)',
                          _ToMarkdown._numpy_params, body, flags=re.MULTILINE)
        return section + '\n-----\n' + body

    @staticmethod
    def numpy(text):
        """
        Convert `text` in numpydoc docstring format to Markdown
        to be further converted later.
        """
        return re.sub(r'^(\w[\w ]+)\n-{3,}\n'
                      r'((?:(?!.+\n-+).*$\n?)*)',
                      _ToMarkdown._numpy_sections, text, flags=re.MULTILINE)

    @staticmethod
    def _is_indented_4_spaces(txt, _3_spaces_or_less=re.compile(r'\n\s{0,3}\S').search):
        return '\n' not in txt or not _3_spaces_or_less(txt)

    @staticmethod
    def _fix_indent(name, type, desc):
        """Maybe fix indent from 2 to 4 spaces."""
        if not _ToMarkdown._is_indented_4_spaces(desc):
            desc = desc.replace('\n', '\n  ')
        return name, type, desc

    @staticmethod
    def indent(indent, text, *, clean_first=False):
        if clean_first:
            text = inspect.cleandoc(text)
        return re.sub(r'\n', '\n' + indent, indent + text.rstrip())

    @staticmethod
    def google(text):
        """
        Convert `text` in Google-style docstring format to Markdown
        to be further converted later.
        """
        def googledoc_sections(match):
            section, body = match.groups('')
            if not body:
                return match.group()
            body = textwrap.dedent(body)
            section = section.title()
            if section in ('Args', 'Attributes'):
                body = re.compile(
                    r'^([\w*]+)(?: \(([\w.,=\[\] -]+)\))?: '
                    r'((?:.*)(?:\n(?: {2,}.*|$))*)', re.MULTILINE).sub(
                    lambda m: _ToMarkdown._deflist(*_ToMarkdown._fix_indent(*m.groups())),
                    inspect.cleandoc('\n' + body)
                )
            elif section in ('Returns', 'Yields', 'Raises', 'Warns'):
                body = re.compile(
                    r'^()([\w.,\[\] ]+): '
                    r'((?:.*)(?:\n(?: {2,}.*|$))*)', re.MULTILINE).sub(
                    lambda m: _ToMarkdown._deflist(*_ToMarkdown._fix_indent(*m.groups())),
                    inspect.cleandoc('\n' + body)
                )
            # Convert into markdown sections. End underlines with '='
            # to avoid matching and re-processing as Numpy sections.
            return '\n{}\n-----=\n{}'.format(section, body)

        text = re.compile(r'^([A-Z]\w+):$\n'
                          r'((?:\n?(?: {2,}.*|$))+)', re.MULTILINE).sub(googledoc_sections, text)
        return text

    @staticmethod
    def _admonition(match, module=None, limit_types=None):
        indent, type, value, text = match.groups()

        if limit_types and type not in limit_types:
            return match.group(0)

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
        if type == 'math':
            return _ToMarkdown.indent(indent,
                                      '\\[ ' + text.strip() + ' \\]',
                                      clean_first=True)

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

        text = _ToMarkdown.indent(indent + '    ', text, clean_first=True)
        return '{}!!! {} "{}"\n{}\n'.format(indent, type, title, text)

    @staticmethod
    def admonitions(text, module, limit_types=None):
        """
        Process reStructuredText's block directives such as
        `.. warning::`, `.. deprecated::`, `.. versionadded::`, etc.
        and turn them into Python-M>arkdown admonitions.

        `limit_types` is optionally a set of directives to limit processing to.

        See: https://python-markdown.github.io/extensions/admonition/
        """
        substitute = partial(re.compile(r'^(?P<indent> *)\.\. ?(\w+)::(?: *(.*))?'
                                        r'((?:\n(?:(?P=indent) +.*| *$))*)', re.MULTILINE).sub,
                             partial(_ToMarkdown._admonition, module=module,
                                     limit_types=limit_types))
        # Apply twice for nested (e.g. image inside warning)
        return substitute(substitute(text))

    @staticmethod
    def _include_file(indent: str, path: str, options: dict, module: pdoc.Module) -> str:
        start_line = int(options.get('start-line', 0))
        end_line = int(options.get('end-line', 0)) or None
        start_after = options.get('start-after')
        end_before = options.get('end-before')

        with open(os.path.normpath(os.path.join(os.path.dirname(module.obj.__file__), path)),
                  encoding='utf-8') as f:
            text = ''.join(list(f)[start_line:end_line])

        if start_after:
            text = text[text.index(start_after) + len(start_after):]
        if end_before:
            text = text[:text.index(end_before)]

        return _ToMarkdown.indent(indent, text)

    @staticmethod
    def _directive_opts(text: str) -> dict:
        return dict(re.findall(r'^ *:([^:]+): *(.*)', text, re.MULTILINE))

    DOCTESTS_RE = re.compile(r'^(?:>>> .*)(?:\n.+)*', re.MULTILINE)

    @staticmethod
    def doctests(text):
        """
        Fence non-fenced (`~~~`) top-level (0-indented)
        doctest blocks so they render as Python code.
        """
        text = _ToMarkdown.DOCTESTS_RE.sub(
            lambda match: '```python-repl\n' + match.group() + '\n```\n', text)
        return text

    @staticmethod
    def raw_urls(text):
        """Wrap URLs in Python-Markdown-compatible <angle brackets>."""
        pattern = re.compile(r"""
            (?P<code_span>                   # matches whole code span
                (?<!`)(?P<fence>`+)(?!`)     # a string of backticks
                .*?
                (?<!`)(?P=fence)(?!`))
            |
            (?P<markdown_link>\[.*?\]\(.*\))  # matches whole inline link
            |
            (?<![<\"\'])                     # does not start with <, ", '
            (?P<url>(?:http|ftp)s?://        # url with protocol
                [^>\s()]+                    # url part before any (, )
                (?:\([^>\s)]*\))*            # optionally url part within parentheses
                [^>\s)]*                     # url part after any )
            )""", re.VERBOSE)

        text = pattern.sub(
            lambda m: ('<' + m.group('url') + '>') if m.group('url') else m.group(), text)
        return text


class _MathPattern(InlineProcessor):
    NAME = 'pdoc-math'
    PATTERN = r'(?<!\S|\\)(?:\\\((.+?)\\\)|\\\[(.+?)\\\]|\$\$(.+?)\$\$)'
    PRIORITY = 181  # Larger than that of 'escape' pattern

    def handleMatch(self, m, data):
        for value, is_block in zip(m.groups(), (False, True, True)):
            if value:
                break
        script = etree.Element('script', type='math/tex' + ('; mode=display' if is_block else ''))
        preview = etree.Element('span', {'class': 'MathJax_Preview'})
        preview.text = script.text = AtomicString(value)
        wrapper = etree.Element('span')
        wrapper.extend([preview, script])
        return wrapper, m.start(0), m.end(0)


def to_html(text: str, *,
            docformat: str = None,
            module: pdoc.Module = None, link: Callable[..., str] = None,
            latex_math: bool = False):
    """
    Returns HTML of `text` interpreted as `docformat`. `__docformat__` is respected
    if present, otherwise Numpydoc and Google-style docstrings are assumed,
    as well as pure Markdown.

    `module` should be the documented module (so the references can be
    resolved) and `link` is the hyperlinking function like the one in the
    example template.
    """
    # Optionally register our math syntax processor
    if not latex_math and _MathPattern.NAME in _md.inlinePatterns:         # type: ignore
        _md.inlinePatterns.deregister(_MathPattern.NAME)                   # type: ignore
    elif latex_math and _MathPattern.NAME not in _md.inlinePatterns:       # type: ignore
        _md.inlinePatterns.register(_MathPattern(_MathPattern.PATTERN),    # type: ignore
                                    _MathPattern.NAME,
                                    _MathPattern.PRIORITY)

    md = to_markdown(text, docformat=docformat, module=module, link=link)
    return _md.reset().convert(md)


def to_markdown(text: str, *,
                docformat: str = None,
                module: pdoc.Module = None, link: Callable[..., str] = None):
    """
    Returns `text`, assumed to be a docstring in `docformat`, converted to markdown.
    `__docformat__` is respected
    if present, otherwise Numpydoc and Google-style docstrings are assumed,
    as well as pure Markdown.

    `module` should be the documented module (so the references can be
    resolved) and `link` is the hyperlinking function like the one in the
    example template.
    """
    if not docformat:
        docformat = str(getattr(getattr(module, 'obj', None), '__docformat__', 'numpy,google '))
        docformat, *_ = docformat.lower().split()
    if not (set(docformat.split(',')) & {'', 'numpy', 'google'}):
        warn('__docformat__ value {!r} in module {!r} not supported. '
             'Supported values are: numpy, google.'.format(docformat, module))
        docformat = 'numpy,google'

    with _fenced_code_blocks_hidden(text) as result:
        text = result[0]

        text = _ToMarkdown.admonitions(text, module)

        if 'google' in docformat:
            text = _ToMarkdown.google(text)

        text = _ToMarkdown.doctests(text)
        text = _ToMarkdown.raw_urls(text)

        # If doing both, do numpy after google, otherwise google-style's
        # headings are incorrectly interpreted as numpy params
        if 'numpy' in docformat:
            text = _ToMarkdown.numpy(text)

        if module and link:
            # Hyperlink markdown code spans not within markdown hyperlinks.
            # E.g. `code` yes, but not [`code`](...). RE adapted from:
            # https://github.com/Python-Markdown/markdown/blob/ada40c66/markdown/inlinepatterns.py#L106
            # Also avoid linking triple-backticked arg names in deflists.
            linkify = partial(_linkify, link=link, module=module, wrap_code=True)
            text = re.sub(r'(?P<inside_link>\[[^\]]*?)?'
                          r'(?:(?<!\\)(?:\\{2})+(?=`)|(?<!\\)(?P<fence>`+)'
                          r'(?P<code>.+?)(?<!`)'
                          r'(?P=fence)(?!`))',
                          lambda m: (m.group()
                                     if m.group('inside_link') or len(m.group('fence')) > 2
                                     else linkify(m)), text)
        result[0] = text
    text = result[0]

    return text


class ReferenceWarning(UserWarning):
    """
    This warning is raised in `to_html` when a object reference in markdown
    doesn't match any documented objects.

    Look for this warning to catch typos / references to obsolete symbols.
    """


def _linkify(match: Match, *, link: Callable[..., str], module: pdoc.Module, wrap_code=False):
    try:
        code_span = match.group('code')
    except IndexError:
        code_span = match.group()

    is_type_annotation = re.match(r'^[`\w\s.,\[\]()]+$', code_span)
    if not is_type_annotation:
        return match.group()

    def handle_refname(match):
        nonlocal link, module
        refname = match.group()
        dobj = module.find_ident(refname)
        if isinstance(dobj, pdoc.External):
            # If this is a single-word reference,
            # most likely an argument name. Skip linking External.
            if '.' not in refname:
                return refname
            # If refname in documentation has a typo or is obsolete, warn.
            # XXX: Assume at least the first part of refname, i.e. the package, is correct.
            module_part = module.find_ident(refname.split('.')[0])
            if not isinstance(module_part, pdoc.External):
                warn('Code reference `{}` in module "{}" does not match any '
                     'documented object.'.format(refname, module.refname),
                     ReferenceWarning, stacklevel=3)
        return link(dobj)

    if wrap_code:
        code_span = code_span.replace('[', '\\[')
    linked = re.sub(r'[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*(?:\(\))?', handle_refname, code_span)
    if wrap_code:
        # Wrapping in HTML <code> as opposed to backticks evaluates markdown */_ markers,
        # so let's escape them in text (but not in HTML tag attributes).
        # Backticks also cannot be used because html returned from `link()`
        # would then become escaped.
        # This finds overlapping matches, https://stackoverflow.com/a/5616910/1090455
        cleaned = re.sub(r'(_(?=[^>]*?(?:<|$)))', r'\\\1', linked)
        return '<code>{}</code>'.format(cleaned)
    return linked


def extract_toc(text: str):
    """
    Returns HTML Table of Contents containing markdown titles in `text`.
    """
    with _fenced_code_blocks_hidden(text) as result:
        result[0] = _ToMarkdown.DOCTESTS_RE.sub('', result[0])
    text = result[0]
    toc, _ = _md.reset().convert('[TOC]\n\n@CUT@\n\n' + text).split('@CUT@', 1)
    if toc.endswith('<p>'):  # CUT was put into its own paragraph
        toc = toc[:-3].rstrip()
    return toc


def format_git_link(template: str, dobj: pdoc.Doc):
    """
    Interpolate `template` as a formatted string literal using values extracted
    from `dobj` and the working environment.
    """
    if not template:
        return None
    try:
        if 'commit' in _str_template_fields(template):
            commit = _git_head_commit()
        abs_path = inspect.getfile(inspect.unwrap(dobj.obj))
        path = _project_relative_path(abs_path)
        lines, start_line = inspect.getsourcelines(dobj.obj)
        end_line = start_line + len(lines) - 1
        url = template.format(**locals())
        return url
    except Exception:
        warn('format_git_link for {} failed:\n{}'.format(dobj.obj, traceback.format_exc()))
        return None


@lru_cache()
def _git_head_commit():
    """
    If the working directory is part of a git repository, return the
    head git commit hash. Otherwise, raise a CalledProcessError.
    """
    process_args = ['git', 'rev-parse', 'HEAD']
    try:
        commit = subprocess.check_output(process_args, universal_newlines=True).strip()
        return commit
    except OSError as error:
        warn("git executable not found on system:\n{}".format(error))
    except subprocess.CalledProcessError as error:
        warn(
            "Ensure pdoc is run within a git repository.\n"
            "`{}` failed with output:\n{}"
            .format(' '.join(process_args), error.output)
        )
    return None


@lru_cache()
def _git_project_root():
    """
    Return the path to project root directory or None if indeterminate.
    """
    path = None
    for cmd in (['git', 'rev-parse', '--show-superproject-working-tree'],
                ['git', 'rev-parse', '--show-toplevel']):
        try:
            path = subprocess.check_output(cmd, universal_newlines=True).rstrip('\r\n')
            if path:
                break
        except (subprocess.CalledProcessError, OSError):
            pass
    path = os.path.normpath(path)
    return path


@lru_cache()
def _project_relative_path(absolute_path):
    """
    Convert an absolute path of a python source file to a project-relative path.
    Assumes the project's path is either the current working directory or
    Python library installation.
    """
    from distutils.sysconfig import get_python_lib
    for prefix_path in (_git_project_root() or os.getcwd(),
                        get_python_lib()):
        common_path = os.path.commonpath([prefix_path, absolute_path])
        if os.path.samefile(common_path, prefix_path):
            # absolute_path is a descendant of prefix_path
            return os.path.relpath(absolute_path, prefix_path)
    raise RuntimeError(
        "absolute path {!r} is not a descendant of the current working directory "
        "or of the system's python library."
        .format(absolute_path)
    )


@lru_cache()
def _str_template_fields(template):
    """
    Return a list of `str.format` field names in a template string.
    """
    from string import Formatter
    return [
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    ]
