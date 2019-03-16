#!/usr/bin/env python3
"""pdoc's CLI interface and helper functions."""

import argparse
import importlib
import inspect
import os
import os.path as path
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import pdoc

parser = argparse.ArgumentParser(
    description="Automatically generate API docs for Python modules.",
)
aa = parser.add_argument
aa('--version', action='version', version='%(prog)s ' + pdoc.__version__)
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
    "--filter",
    type=str,
    metavar='STRING',
    default=None,
    help="Comma-separated list of filters. When specified, "
         "only identifiers containing the specified string "
         "will be shown in the output. Search is case sensitive. "
         "Has no effect when --http is set.",
)
aa("--html", action="store_true", help="When set, the output will be HTML formatted.")
aa(
    "--html-dir",
    type=str,
    metavar='DIR',
    default="html",
    help="The directory to output HTML files to (default: ./html). "
         "Only in effect when --html is.",
)
aa(
    "--html-no-source",
    action="store_true",
    help="When set, source code will not be viewable in the generated HTML. "
    "This can speed up the time required to document large modules.",
)
aa(
    "--overwrite",
    action="store_true",
    help="Overwrites any existing HTML files instead of producing an error.",
)
aa(
    "--external-links",
    action="store_true",
    help="When set, identifiers to external modules are turned into links. "
         "This is automatically set when --http is.",
)
aa(
    "--template-dir",
    type=str,
    metavar='DIR',
    default=None,
    help="Specify a directory containing Mako templates "
         "(html.mako or text.mako, and any templates they include). "
         "Alternatively, put your templates in $XDG_CONFIG_HOME/pdoc and "
         "pdoc will automatically find them.",
)
aa(
    "--link-prefix",
    type=str,
    metavar='STRING',
    default="",
    help="A prefix to use for every link in the generated documentation. "
         "No link prefix results in all links being relative. "
         "No effect when combined with --http.",
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
            "'{}' doesn't match '[HOST]:[PORT]'. "
            "Specify `--http :` to use default hostname and port.".format(s))
    return s


aa(
    "--http",
    default='',
    type=_check_host_port,
    metavar='HOST:PORT',
    help="When set, pdoc will run as an HTTP server providing documentation "
         "for specified modules. If you just want to use the default hostname "
         "and port ({}:{}), set the parameter to :.".format(DEFAULT_HOST, DEFAULT_PORT),
)

args = argparse.Namespace()


class WebDoc(BaseHTTPRequestHandler):
    args = None  # Set before server instantiated

    def do_HEAD(self):
        if self.path != "/":
            out = self.html()
            if out is None:
                self.send_response(404)
                self.end_headers()
                return

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        # Deny favicon shortcut early.
        if self.path == "/favicon.ico":
            return None

        importlib.invalidate_caches()
        code = 200
        if self.path == "/":
            modules = [pdoc.import_module(module)
                       for module in self.args.modules]
            modules = sorted((module.__name__, inspect.getdoc(module))
                             for module in modules)
            out = pdoc._render_template('/html.mako',
                                        modules=modules,
                                        link_prefix=self.args.link_prefix)
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
                print("Generating HTML for %s on the fly..." % import_path, file=sys.stderr)
                try:
                    out = pdoc.html(import_path.split(".")[0])
                except Exception as e:
                    print('Error generating docs: {}'.format(e), file=sys.stderr)
                    # All hope is lost.
                    code = 404
                    out = "External identifier <code>%s</code> not found." % import_path
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
            out = self.html()
            if out is None:
                code = 404
                out = "Module <code>%s</code> not found." % self.import_path_from_req_url

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
        # TODO: pass extra pdoc.html() params
        return pdoc.html(self.import_path_from_req_url, http_server=True)

    def resolve_ext(self, import_path):
        def exists(p):
            p = path.join(args.html_dir, p)
            pkg = path.join(p, pdoc._URL_PACKAGE_SUFFIX.lstrip('/'))
            mod = p + pdoc._URL_MODULE_SUFFIX

            if path.isfile(pkg):
                return pkg[len(args.html_dir):]
            elif path.isfile(mod):
                return mod[len(args.html_dir):]
            return None

        parts = import_path.split(".")
        for i in range(len(parts), 0, -1):
            p = path.join(*parts[0:i])
            realp = exists(p)
            if realp is not None:
                return "/%s#%s" % (realp.lstrip("/"), import_path)
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


def module_html_path(m: pdoc.Module):
    return path.join(args.html_dir, *m.url().split('/'))


def _quit_if_exists(m: pdoc.Module):
    if args.overwrite:
        return

    paths = [module_html_path(m)]
    if m.is_package:  # If package, make sure the dir doesn't exist either
        paths.append(path.dirname(paths[0]))

    for pth in paths:
        if path.lexists(pth):
            print("File '%s' already exists. Delete it or run with --overwrite" % pth,
                  file=sys.stderr)
            sys.exit(1)


def write_html_files(m: pdoc.Module):
    f = module_html_path(m)

    dirpath = path.dirname(f)
    if not os.access(dirpath, os.R_OK):
        os.makedirs(dirpath)

    try:
        with open(f, 'w+', encoding='utf-8') as w:
            w.write(m.html(
                external_links=args.external_links,
                link_prefix=args.link_prefix,
                source=not args.html_no_source,
            ))
    except Exception:
        try:
            os.unlink(f)
        except Exception:
            pass
        raise

    for submodule in m.submodules():
        write_html_files(submodule)


def main(_args=None):
    """ Command-line entry point """
    global args
    args = _args or parser.parse_args()

    if args.close_stdin:
        sys.stdin.close()

    if args.template_dir is not None:
        if not path.isdir(args.template_dir):
            print('Error: Template dir {!r} is not a directory'.format(args.template_dir),
                  file=sys.stderr)
            sys.exit(1)
        pdoc.tpl_lookup.directories.insert(0, args.template_dir)

    # Support loading modules specified as python paths relative to cwd
    sys.path.append(os.getcwd())

    if args.http:
        args.html = True
        args.external_links = True
        args.overwrite = True
        args.link_prefix = "/"

        # Run the HTTP server.
        WebDoc.args = args  # Pass params to HTTPServer xP

        host, _, port = args.http.partition(':')
        host = host or DEFAULT_HOST
        port = int(port or DEFAULT_PORT)

        print('Starting pdoc server on {}:{}'.format(host, port), file=sys.stderr)
        httpd = HTTPServer((host, port), WebDoc)
        print("pdoc server ready at http://%s:%d" % (host, port), file=sys.stderr)

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

    modules = [pdoc.Module(pdoc.import_module(module),
                           docfilter=docfilter)
               for module in args.modules]
    pdoc.link_inheritance()

    for module in modules:
        if args.html:
            _quit_if_exists(module)
            write_html_files(module)
        else:
            sys.stdout.write(module.text())
            # Two blank lines between two modules' texts
            sys.stdout.write(os.linesep * (1 + 2 * int(module != modules[-1])))


if __name__ == "__main__":
    main(parser.parse_args())
