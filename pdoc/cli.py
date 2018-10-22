#!/usr/bin/env python2

from __future__ import absolute_import, division, print_function
import argparse

try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
import codecs
import datetime
import imp
import os
import os.path as path
import pkgutil
import re
import subprocess
import sys

import pdoc
from pdoc import import_module

# `xrange` is `range` with Python3.
try:
    xrange = xrange
except NameError:
    xrange = range

version_suffix = "%d.%d" % (sys.version_info[0], sys.version_info[1])

parser = argparse.ArgumentParser(
    description="Automatically generate API docs for Python modules.",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
    default=".",
    help="The directory to output HTML files to. This option is ignored when "
    "outputting documentation as plain text.",
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
    "This is automatically set when using --http.",
)
aa(
    "--template-dir",
    type=str,
    default=None,
    help="Specify a directory containing Mako templates. "
    "Alternatively, put your templates in $XDG_CONFIG_HOME/pdoc and "
    "pdoc will automatically find them.",
)
aa(
    "--link-prefix",
    type=str,
    default="",
    help="A prefix to use for every link in the generated documentation. "
    "No link prefix results in all links being relative. "
    "Has no effect when combined with --http.",
)
aa(
    "--only-pypath",
    action="store_true",
    help="When set, only modules in your PYTHONPATH will be documented.",
)
aa(
    "--http",
    action="store_true",
    help="When set, pdoc will run as an HTTP server providing documentation "
    "of all installed modules. Only modules found in PYTHONPATH will be "
    "listed.",
)
aa(
    "--http-host",
    type=str,
    default="localhost",
    help="The host on which to run the HTTP server.",
)
aa(
    "--http-port",
    type=int,
    default=8080,
    help="The port on which to run the HTTP server.",
)
aa("--http-html", action="store_true", help="Internal use only. Do not set.")


class WebDoc(BaseHTTPRequestHandler):
    def do_HEAD(self):
        if self.path != "/":
            out = self.html()
            if out is None:
                self.send_response(404)
                self.end_headers()
                return

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            modules = []
            for (imp, name, ispkg) in pkgutil.iter_modules(pdoc.import_path):
                if name == "setup" and not ispkg:
                    continue
                modules.append((name, quick_desc(imp, name, ispkg)))
            modules = sorted(modules, key=lambda x: x[0].lower())

            out = pdoc.tpl_lookup.get_template("/html.mako")
            out = out.render(modules=modules, link_prefix=args.link_prefix)
            out = out.strip()
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
                _eprint("Generating HTML for %s on the fly..." % import_path)
                try:
                    process_html_out(import_path.split(".")[0])
                except subprocess.CalledProcessError as e:
                    _eprint(
                        'Could not run "%s" (exit code: %d): %s'
                        % (" ".join(e.cmd), e.returncode, e.output)
                    )

                # Try looking once more.
                resolved = self.resolve_ext(import_path)
            if resolved is None:  # All hope is lost.
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.echo(
                    "External identifier <code>%s</code> not found." % import_path
                )
                return
            self.send_response(302)
            self.send_header("Location", resolved)
            self.end_headers()
            return
        else:
            out = self.html()
            if out is None:
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()

                err = "Module <code>%s</code> not found." % self.import_path
                self.echo(err)
                return

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.echo(out)

    def echo(self, s):
        self.wfile.write(s.encode("utf-8"))

    def html(self):
        """
        Retrieves and sends the HTML belonging to the path given in
        URL. This method is smart and will look for HTML files already
        generated and account for whether they are stale compared to
        the source code.
        """

        # Deny favico shortcut early.
        if self.path == "/favicon.ico":
            return None

        # Look for the module file without importing it.
        impath = self.import_path
        try:
            mfile = pkgutil.get_loader(self.import_path).get_filename()
        except Exception as e:
            _eprint("Could not load %s: %s" % (impath, e))
            mfile = None

        # Check the file system first before trying an import.
        fp = self.file_path
        if last_modified(mfile) < last_modified(fp) and os.access(fp, os.R_OK):
            with codecs.open(fp, "r", "utf-8") as f:
                return f.read()

        # Regenerate the HTML by shelling out to pdoc.
        # This ensures that the documentation is generated from a fresh import.
        _eprint("Generating HTML for %s" % impath)
        try:
            process_html_out(impath)
        except subprocess.CalledProcessError as e:
            _eprint(
                'Could not run "%s" (exit code: %d): %s'
                % (" ".join(e.cmd), e.returncode, e.output)
            )
            return None

        with codecs.open(self.file_path, "r", "utf-8") as f:
            return f.read()

    def resolve_ext(self, import_path):
        def exists(p):
            p = path.join(args.html_dir, p)
            pkg = path.join(p, pdoc.html_package_name)
            mod = p + pdoc.html_module_suffix

            if path.isfile(pkg):
                return pkg[len(args.html_dir) :]
            elif path.isfile(mod):
                return mod[len(args.html_dir) :]
            return None

        parts = import_path.split(".")
        for i in xrange(len(parts), 0, -1):
            p = path.join(*parts[0:i])
            realp = exists(p)
            if realp is not None:
                return "/%s#%s" % (realp.lstrip("/"), import_path)
        return None

    @property
    def file_path(self):
        fp = path.join(args.html_dir, *self.import_path.split("."))
        pkgp = path.join(fp, pdoc.html_package_name)
        if path.isdir(fp) and path.isfile(pkgp):
            fp = pkgp
        else:
            fp += pdoc.html_module_suffix
        return fp

    @property
    def import_path(self):
        pieces = self.clean_path.split("/")
        if pieces[-1].startswith(pdoc.html_package_name):
            pieces = pieces[:-1]
        if pieces[-1].endswith(pdoc.html_module_suffix):
            pieces[-1] = pieces[-1][: -len(pdoc.html_module_suffix)]
        return ".".join(pieces)

    @property
    def clean_path(self):
        new, _ = re.subn("//+", "/", self.path)
        if "#" in new:
            new = new[0 : new.index("#")]
        return new.strip("/")

    def address_string(self):
        return "%s:%s" % (self.client_address[0], self.client_address[1])


def quick_desc(imp, name, ispkg):
    if not hasattr(imp, "path"):
        # See issue #7.
        return ""

    if ispkg:
        fp = path.join(imp.path, name, "__init__.py")
    else:
        fp = path.join(imp.path, "%s.py" % name)
    if os.path.isfile(fp):
        with codecs.open(fp, "r", "utf-8") as f:
            quotes = None
            doco = []
            for i, line in enumerate(f):
                if i == 0:
                    if len(line) >= 3 and line[0:3] in ("'''", '"""'):
                        quotes = line[0:3]
                        line = line[3:]
                    else:
                        break
                line = line.rstrip()
                if line.endswith(quotes):
                    doco.append(line[0:-3])
                    break
                else:
                    doco.append(line)
            desc = "\n".join(doco)
            if len(desc) > 200:
                desc = desc[0:200] + "..."
            return desc
    return ""


def _eprint(*args, **kwargs):
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)


def last_modified(fp):
    try:
        return datetime.datetime.fromtimestamp(os.stat(fp).st_mtime)
    except:
        return datetime.datetime.min


def module_file(m):
    mbase = path.join(args.html_dir, *m.name.split("."))
    if m.is_package:
        return path.join(mbase, pdoc.html_package_name)
    else:
        return "%s%s" % (mbase, pdoc.html_module_suffix)


def quit_if_exists(m):
    def check_file(f):
        if os.access(f, os.R_OK):
            _eprint("%s already exists. Delete it or run with --overwrite" % f)
            sys.exit(1)

    if args.overwrite:
        return
    f = module_file(m)
    check_file(f)

    # If this is a package, make sure the package directory doesn't exist
    # either.
    if m.is_package:
        check_file(path.dirname(f))


def html_out(m, html=True):
    f = module_file(m)
    if not html:
        f = module_file(m).replace(".html", ".md")
    dirpath = path.dirname(f)
    if not os.access(dirpath, os.R_OK):
        os.makedirs(dirpath)
    try:
        with codecs.open(f, "w+", "utf-8") as w:
            if not html:
                out = m.text()
            else:
                out = m.html(
                    external_links=args.external_links,
                    link_prefix=args.link_prefix,
                    http_server=args.http_html,
                    source=not args.html_no_source,
                )
            print(out, file=w)
    except Exception:
        try:
            os.unlink(f)
        except:
            pass
        raise
    for submodule in m.submodules():
        html_out(submodule, html)


def process_html_out(impath):
    # This unfortunate kludge is the only reasonable way I could think of
    # to support reloading of modules. It's just too difficult to get
    # modules to reload in the same process.

    cmd = [
        sys.executable,
        path.realpath(__file__),
        "--html",
        "--html-dir",
        args.html_dir,
        "--http-html",
        "--overwrite",
        "--link-prefix",
        args.link_prefix,
    ]
    if args.external_links:
        cmd.append("--external-links")
    if args.only_pypath:
        cmd.append("--only-pypath")
    if args.html_no_source:
        cmd.append("--html-no-source")
    if args.template_dir:
        cmd.append("--template-dir")
        cmd.append(args.template_dir)
    cmd.append(impath)

    # Can we make a good faith attempt to support 2.6?
    # YES WE CAN!
    p = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    out = p.communicate()[0].strip().decode("utf-8")
    if p.returncode > 0:
        err = subprocess.CalledProcessError(p.returncode, cmd)
        err.output = out
        raise err
    if len(out) > 0:
        print(out)


def main(_args=None):
    """ Command-line entry point """
    global args
    args = _args or parser.parse_args()

    # We close stdin because some modules, upon import, are not very polite
    # and block on stdin.
    try:
        sys.stdin.close()
    except:
        pass

    if args.template_dir is not None:
        pdoc.tpl_lookup.directories.insert(0, args.template_dir)
    if args.http:
        args.html = True
        args.external_links = True
        args.overwrite = True
        args.link_prefix = "/"

    # If PYTHONPATH is set, let it override everything if we want it to.
    pypath = os.getenv("PYTHONPATH")
    if args.only_pypath and pypath is not None and len(pypath) > 0:
        pdoc.import_path = pypath.split(path.pathsep)

    if args.http:
        # Run the HTTP server.
        httpd = HTTPServer((args.http_host, args.http_port), WebDoc)
        print(
            "pdoc server ready at http://%s:%d" % (args.http_host, args.http_port),
            file=sys.stderr,
        )

        httpd.serve_forever()
        httpd.server_close()
        sys.exit(0)

    docfilter = None
    if args.filter and args.filter.strip():
        def docfilter(obj, _filters=args.filter.strip().split(',')):
            return any(f in obj.refname or
                       isinstance(obj, pdoc.Class) and f in obj.doc
                       for f in _filters)

    # Support loading modules specified as python paths relative to cwd
    sys.path.append(os.getcwd())

    for module in args.modules:
        module = pdoc.Module(import_module(module),
                             docfilter=docfilter,
                             allsubmodules=args.all_submodules)
        if args.html:
            quit_if_exists(module)
            html_out(module, args.html)
        else:
            sys.stdout.write(module.text())
            # Two blank lines between two modules' texts
            sys.stdout.write(os.linesep * (1 + 2 * int(module != modules[-1])))


if __name__ == "__main__":
    main(parser.parse_args())
