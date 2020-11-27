#!/usr/bin/env python3
"""pdoc's CLI interface and helper functions."""

import argparse
import ast
import importlib
import inspect
import os
import os.path as path
import json
import re
import sys
import warnings
from contextlib import contextmanager
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Sequence
from warnings import warn

import pdoc

parser = argparse.ArgumentParser(
    description="Automatically generate API docs for Python modules.",
    epilog="Further documentation is available at <https://pdoc3.github.io/pdoc/doc>.",
)
aa = parser.add_argument
mode_aa = parser.add_mutually_exclusive_group().add_argument

aa(
    '--version', action='version', version='%(prog)s ' + pdoc.__version__)
aa(
    "modules",
    type=str,
    metavar='MODULE',
    nargs="+",
    help="The Python module name. This may be an import path resolvable in "
    "the current environment, or a file path to a Python module or "
    "package.",
)
aa(
    "-c", "--config",
    type=str,
    metavar='OPTION=VALUE',
    action='append',
    default=[],
    help="Override template options. This is an alternative to using "
         "a custom config.mako file in --template-dir. This option "
         "can be specified multiple times.",
)
aa(
    "--filter",
    type=str,
    metavar='STRING',
    default=None,
    help="Comma-separated list of filters. When specified, "
         "only identifiers containing the specified string "
         "will be shown in the output. Search is case sensitive. "
         "Has no effect when --http is set.",
)
aa(
    "-f", "--force",
    action="store_true",
    help="Overwrite any existing generated (--output-dir) files.",
)
mode_aa(
    "--html",
    action="store_true",
    help="When set, the output will be HTML formatted.",
)
mode_aa(
    "--pdf",
    action="store_true",
    help="When set, the specified modules will be printed to standard output, "
         "formatted in Markdown-Extra, compatible with most "
         "Markdown-(to-HTML-)to-PDF converters.",
)
aa(
    "--html-dir",
    type=str,
    help=argparse.SUPPRESS,
)
aa(
    "-o", "--output-dir",
    type=str,
    metavar='DIR',
    help="The directory to output generated HTML/markdown files to "
         "(default: ./html for --html).",
)
aa(
    "--html-no-source",
    action="store_true",
    help=argparse.SUPPRESS,
)
aa(
    "--overwrite",
    action="store_true",
    help=argparse.SUPPRESS,
)
aa(
    "--external-links",
    action="store_true",
    help=argparse.SUPPRESS,
)
aa(
    "--template-dir",
    type=str,
    metavar='DIR',
    default=None,
    help="Specify a directory containing Mako templates "
         "(html.mako, text.mako, config.mako and/or any templates they include). "
         "Alternatively, put your templates in $XDG_CONFIG_HOME/pdoc and "
         "pdoc will automatically find them.",
)
aa(
    "--link-prefix",
    type=str,
    help=argparse.SUPPRESS,
)
aa(
    "--close-stdin",
    action="store_true",
    help="When set, stdin will be closed before importing, to account for "
         "ill-behaved modules that block on stdin."
)

DEFAULT_HOST, DEFAULT_PORT = 'localhost', 8080


def _check_host_port(s):
    if s and ':' not in s:
        raise argparse.ArgumentTypeError(
            f"'{s}' doesn't match '[HOST]:[PORT]'. "
            "Specify `--http :` to use default hostname and port.")
    return s


aa(
    "--http",
    default='',
    type=_check_host_port,
    metavar='HOST:PORT',
    help="When set, pdoc will run as an HTTP server providing documentation "
         "for specified modules. If you just want to use the default hostname "
         f"and port ({DEFAULT_HOST}:{DEFAULT_PORT}), set the parameter to :.",
)
aa(
    "--skip-errors",
    action="store_true",
    help="Upon unimportable modules, warn instead of raising."
)

args = argparse.Namespace()


class _WebDoc(BaseHTTPRequestHandler):
    args = None  # Set before server instantiated
    template_config = None

    def do_HEAD(self):
        status = 200
        if self.path != "/":
            status = self.check_modified()

        self.send_response(status)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

    def check_modified(self):
        try:
            module = pdoc.import_module(self.import_path_from_req_url)
            new_etag = str(os.stat(module.__file__).st_mtime)
        except ImportError:
            return 404

        old_etag = self.headers.get('If-None-Match', new_etag)
        if old_etag == new_etag:
            # Don't log repeating checks
            self.log_request = lambda *args, **kwargs: None
            return 304

        return 205

    def do_GET(self):
        # Deny favicon shortcut early.
        if self.path == "/favicon.ico":
            return None

        importlib.invalidate_caches()
        code = 200
        if self.path == "/":
            modules = [pdoc.import_module(module, reload=True)
                       for module in self.args.modules]
            modules = sorted((module.__name__, inspect.getdoc(module))
                             for module in modules)
            out = pdoc._render_template('/html.mako',
                                        modules=modules,
                                        **self.template_config)
        elif self.path.endswith(".ext"):
            # External links are a bit weird. You should view them as a giant
            # hack. Basically, the idea is to "guess" where something lives
            # when documenting another module and hope that guess can actually
            # track something down in a more global context.
            #
            # The idea here is to start specific by looking for HTML that
            # exists that matches the full external path given. Then trim off
            # one component at the end and try again.
            #
            # If no HTML is found, then we ask `pdoc` to do its thang on the
            # parent module in the external path. If all goes well, that
            # module will then be able to find the external identifier.

            import_path = self.path[:-4].lstrip("/")
            resolved = self.resolve_ext(import_path)
            if resolved is None:  # Try to generate the HTML...
                print(f"Generating HTML for {import_path} on the fly...", file=sys.stderr)
                try:
                    out = pdoc.html(import_path.split(".")[0], **self.template_config)
                except Exception as e:
                    print(f'Error generating docs: {e}', file=sys.stderr)
                    # All hope is lost.
                    code = 404
                    out = f"External identifier <code>{import_path}</code> not found."
            else:
                return self.redirect(resolved)
        # Redirect '/pdoc' to '/pdoc/' so that relative links work
        # (results in '/pdoc/cli.html' instead of 'cli.html')
        elif not self.path.endswith(('/', '.html')):
            return self.redirect(self.path + '/')
        # Redirect '/pdoc/index.html' to '/pdoc/' so it's more pretty
        elif self.path.endswith(pdoc._URL_PACKAGE_SUFFIX):
            return self.redirect(self.path[:-len(pdoc._URL_PACKAGE_SUFFIX)] + '/')
        else:
            try:
                out = self.html()
            except Exception:
                import traceback
                from html import escape
                code = 404
                out = (
                    "Error importing module "
                    f"<code>{self.import_path_from_req_url}</code>:\n\n"
                    f"<pre>{escape(traceback.format_exc())}</pre>"
                )
                out = out.replace('\n', '<br>')

        self.send_response(code)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.echo(out)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def echo(self, s):
        self.wfile.write(s.encode("utf-8"))

    def html(self):
        """
        Retrieves and sends the HTML belonging to the path given in
        URL. This method is smart and will look for HTML files already
        generated and account for whether they are stale compared to
        the source code.
        """
        return pdoc.html(self.import_path_from_req_url,
                         reload=True, http_server=True, external_links=True,
                         skip_errors=args.skip_errors,
                         **self.template_config)

    def resolve_ext(self, import_path):
        def exists(p):
            p = path.join(args.output_dir, p)
            pkg = path.join(p, pdoc._URL_PACKAGE_SUFFIX.lstrip('/'))
            mod = p + pdoc._URL_MODULE_SUFFIX

            if path.isfile(pkg):
                return pkg[len(args.output_dir):]
            elif path.isfile(mod):
                return mod[len(args.output_dir):]
            return None

        parts = import_path.split(".")
        for i in range(len(parts), 0, -1):
            p = path.join(*parts[0:i])
            realp = exists(p)
            if realp is not None:
                return f"/{realp.lstrip('/')}#{import_path}"
        return None

    @property
    def import_path_from_req_url(self):
        pth = self.path.split('#')[0].lstrip('/')
        for suffix in ('/',
                       pdoc._URL_PACKAGE_SUFFIX,
                       pdoc._URL_INDEX_MODULE_SUFFIX,
                       pdoc._URL_MODULE_SUFFIX):
            if pth.endswith(suffix):
                pth = pth[:-len(suffix)]
                break
        return pth.replace('/', '.')


def module_path(m: pdoc.Module, ext: str):
    return path.join(args.output_dir, *re.sub(r'\.html$', ext, m.url()).split('/'))


def _quit_if_exists(m: pdoc.Module, ext: str):
    if args.force:
        return

    paths = [module_path(m, ext)]
    if m.is_package:  # If package, make sure the dir doesn't exist either
        paths.append(path.dirname(paths[0]))

    for pth in paths:
        if path.lexists(pth):
            print(f"File '{pth}' already exists. Delete it, or run with --force", file=sys.stderr)
            sys.exit(1)


@contextmanager
def _open_write_file(filename):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            yield f
            print(filename)  # print created file path to stdout
    except Exception:
        try:
            os.unlink(filename)
        except Exception:
            pass
        raise


def recursive_write_files(m: pdoc.Module, ext: str, **kwargs):
    assert ext in ('.html', '.md')
    filepath = module_path(m, ext=ext)

    dirpath = path.dirname(filepath)
    if not os.access(dirpath, os.R_OK):
        os.makedirs(dirpath)

    with _open_write_file(filepath) as f:
        if ext == '.html':
            f.write(m.html(**kwargs))
        elif ext == '.md':
            f.write(m.text(**kwargs))

    for submodule in m.submodules():
        recursive_write_files(submodule, ext=ext, **kwargs)


def _flatten_submodules(modules: Sequence[pdoc.Module]):
    for module in modules:
        yield module
        for submodule in module.submodules():
            yield from _flatten_submodules((submodule,))


def _print_pdf(modules, **kwargs):
    modules = list(_flatten_submodules(modules))
    print(pdoc._render_template('/pdf.mako', modules=modules, **kwargs))


def _warn_deprecated(option, alternative='', use_config_mako=False):
    msg = f'Program option `{option}` is deprecated.'
    if alternative:
        msg += ' Use `' + alternative + '`'
        if use_config_mako:
            msg += ' or override config.mako template'
        msg += '.'
    warn(msg, DeprecationWarning, stacklevel=2)


def _generate_lunr_search(modules: List[pdoc.Module],
                          index_docstrings: bool,
                          template_config: dict):
    """Generate index.js for search"""

    def trim_docstring(docstring):
        return re.sub(r'''
            \s+|                   # whitespace sequences
            \s+[-=~]{3,}\s+|       # title underlines
            ^[ \t]*[`~]{3,}\w*$|   # code blocks
            \s*[`#*]+\s*|          # common markdown chars
            \s*([^\w\d_>])\1\s*|   # sequences of punct of the same kind
            \s*</?\w*[^>]*>\s*     # simple HTML tags
        ''', ' ', docstring, flags=re.VERBOSE | re.MULTILINE)

    def recursive_add_to_index(dobj):
        info = {
            'ref': dobj.refname,
            'url': to_url_id(dobj.module),
        }
        if index_docstrings:
            info['doc'] = trim_docstring(dobj.docstring)
        if isinstance(dobj, pdoc.Function):
            info['func'] = 1
        index.append(info)
        for member_dobj in getattr(dobj, 'doc', {}).values():
            recursive_add_to_index(member_dobj)

    @lru_cache()
    def to_url_id(module):
        url = module.url()
        if url not in url_cache:
            url_cache[url] = len(url_cache)
        return url_cache[url]

    index = []  # type: List[Dict]
    url_cache = {}  # type: Dict[str, int]
    for top_module in modules:
        recursive_add_to_index(top_module)
    urls = sorted(url_cache.keys(), key=url_cache.__getitem__)

    main_path = args.output_dir
    with _open_write_file(path.join(main_path, 'index.js')) as f:
        f.write("URLS=")
        json.dump(urls, f, indent=0, separators=(',', ':'))
        f.write(";\nINDEX=")
        json.dump(index, f, indent=0, separators=(',', ':'))

    # Generate search.html
    with _open_write_file(path.join(main_path, 'doc-search.html')) as f:
        rendered_template = pdoc._render_template('/search.mako', **template_config)
        f.write(rendered_template)


def main(_args=None):
    """ Command-line entry point """
    global args
    args = _args or parser.parse_args()

    warnings.simplefilter("once", DeprecationWarning)

    if args.close_stdin:
        sys.stdin.close()

    if (args.html or args.http) and not args.output_dir:
        args.output_dir = 'html'

    if args.html_dir:
        _warn_deprecated('--html-dir', '--output-dir')
        args.output_dir = args.html_dir
    if args.overwrite:
        _warn_deprecated('--overwrite', '--force')
        args.force = args.overwrite

    template_config = {}
    for config_str in args.config:
        try:
            key, value = config_str.split('=', 1)
            value = ast.literal_eval(value)
            template_config[key] = value
        except Exception:
            raise ValueError(
                f'Error evaluating --config statement "{config_str}". '
                'Make sure string values are quoted?'
            )

    if args.html_no_source:
        _warn_deprecated('--html-no-source', '-c show_source_code=False', True)
        template_config['show_source_code'] = False
    if args.link_prefix:
        _warn_deprecated('--link-prefix', '-c link_prefix="foo"', True)
        template_config['link_prefix'] = args.link_prefix
    if args.external_links:
        _warn_deprecated('--external-links')
        template_config['external_links'] = True

    if args.template_dir is not None:
        if not path.isdir(args.template_dir):
            print(f'Error: Template dir {args.template_dir!r} is not a directory', file=sys.stderr)
            sys.exit(1)
        pdoc.tpl_lookup.directories.insert(0, args.template_dir)

    # Support loading modules specified as python paths relative to cwd
    sys.path.append(os.getcwd())

    # Virtual environment handling for pdoc script run from system site
    try:
        venv_dir = os.environ['VIRTUAL_ENV']
    except KeyError:
        pass  # pdoc was not invoked while in a virtual environment
    else:
        from glob import glob
        from distutils.sysconfig import get_python_lib
        libdir = get_python_lib(prefix=venv_dir)
        sys.path.append(libdir)
        # Resolve egg-links from `setup.py develop` or `pip install -e`
        # XXX: Welcome a more canonical approach
        for pth in glob(path.join(libdir, '*.egg-link')):
            try:
                with open(pth) as f:
                    sys.path.append(path.join(libdir, f.readline().rstrip()))
            except IOError:
                warn(f'Invalid egg-link in venv: {pth!r}')

    if args.http:
        template_config['link_prefix'] = "/"

        # Run the HTTP server.
        _WebDoc.args = args  # Pass params to HTTPServer xP
        _WebDoc.template_config = template_config

        host, _, port = args.http.partition(':')
        host = host or DEFAULT_HOST
        port = int(port or DEFAULT_PORT)

        print(f'Starting pdoc server on {host}:{port}', file=sys.stderr)
        httpd = HTTPServer((host, port), _WebDoc)
        print(f"pdoc server ready at http://{host}:{port}", file=sys.stderr)

        # Allow tests to perform `pdoc.cli._httpd.shutdown()`
        global _httpd
        _httpd = httpd

        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
            sys.exit(0)

    docfilter = None
    if args.filter and args.filter.strip():
        def docfilter(obj, _filters=args.filter.strip().split(',')):
            return any(f in obj.refname or
                       isinstance(obj, pdoc.Class) and f in obj.doc
                       for f in _filters)

    modules = [pdoc.Module(module, docfilter=docfilter,
                           skip_errors=args.skip_errors)
               for module in args.modules]
    pdoc.link_inheritance()

    if args.pdf:
        _print_pdf(modules, **template_config)
        import textwrap
        PANDOC_CMD = textwrap.indent(_PANDOC_COMMAND, '    ')
        print(f"""
PDF-ready markdown written to standard output.
                              ^^^^^^^^^^^^^^^
Convert this file to PDF using e.g. Pandoc:

{PANDOC_CMD}

or using Python-Markdown and Chrome/Chromium/WkHtmlToPDF:

    markdown_py --extension=meta         \\
                --extension=abbr         \\
                --extension=attr_list    \\
                --extension=def_list     \\
                --extension=fenced_code  \\
                --extension=footnotes    \\
                --extension=tables       \\
                --extension=admonition   \\
                --extension=smarty       \\
                --extension=toc          \\
                pdf.md > pdf.html

    chromium --headless --disable-gpu --print-to-pdf=pdf.pdf pdf.html

    wkhtmltopdf --encoding utf8 -s A4 --print-media-type pdf.html pdf.pdf

or similar, at your own discretion.""",
              file=sys.stderr)
        sys.exit(0)

    for module in modules:
        if args.html:
            _quit_if_exists(module, ext='.html')
            recursive_write_files(module, ext='.html', **template_config)
        elif args.output_dir:  # Generate text files
            _quit_if_exists(module, ext='.md')
            recursive_write_files(module, ext='.md', **template_config)
        else:
            sys.stdout.write(module.text(**template_config))
            # Two blank lines between two modules' texts
            sys.stdout.write(os.linesep * (1 + 2 * int(module != modules[-1])))

    lunr_config = pdoc._get_config(**template_config).get('lunr_search')
    if lunr_config is not None:
        _generate_lunr_search(
            modules, lunr_config.get("index_docstrings", True), template_config)


_PANDOC_COMMAND = '''\
pandoc --metadata=title:"MyProject Documentation"               \\
       --from=markdown+abbreviations+tex_math_single_backslash  \\
       --pdf-engine=xelatex --variable=mainfont:"DejaVu Sans"   \\
       --toc --toc-depth=4 --output=pdf.pdf  pdf.md\
'''


if __name__ == "__main__":
    main(parser.parse_args())
