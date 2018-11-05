"""
Helper functions for HTML output.
"""
import re
from functools import partial


def minify_css(css,
               _whitespace=partial(re.compile(r'\s*([,{:;}])\s*').sub, r'\1'),
               _comments=partial(re.compile(r'/\*.*?\*/', flags=re.DOTALL).sub, ''),
               _trailing_semicolon=partial(re.compile(r';\s*}').sub, '}')):
    """
    Minify CSS by removing extraneous whitespace, comments, and trailing semicolons.
    """
    return _trailing_semicolon(_whitespace(_comments(css))).strip()


def minify_html(html,
                _contains_pre=re.compile(r'<pre\b', re.IGNORECASE).search,
                _ends_pre=re.compile(r'</pre\b', re.IGNORECASE).search,
                _norm_space=partial(re.compile(r'\s\s+').sub, ' ')):
    """
    Minify HTML by replacing all consecutive whitespace with a single space
    (or newline) character, except inside `<pre>` tags.
    """
    out = []
    lines = iter(html.split('\n'))
    for line in lines:
        if _contains_pre(line):
            out.append(line.lstrip())
            while not _ends_pre(line) or _contains_pre(line):
                line = next(lines)
                out.append(line)
            out[-1] = out[-1].rstrip()
            continue
        line = _norm_space(line.strip())
        if line:
            out.append(line)
    return '\n'.join(out)
