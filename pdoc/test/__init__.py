import os
import signal
import subprocess
import sys
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from glob import glob
from io import StringIO
from itertools import chain
from random import randint
from tempfile import TemporaryDirectory
from time import sleep
from urllib.request import urlopen

import pdoc
from pdoc.cli import main, parser

TESTS_BASEDIR = os.path.abspath(os.path.dirname(__file__) or '.')
EXAMPLE_MODULE = 'example_pkg'

sys.path.insert(0, TESTS_BASEDIR)


@contextmanager
def temp_dir():
    with TemporaryDirectory(prefix='pdoc-test-') as path:
        yield path


@contextmanager
def chdir(path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)


def run(*args, _check=True, **kwargs) -> int:
    params = (('--' + key.replace('_', '-'), value)
              for key, value in kwargs.items())
    params = list(filter(None, chain.from_iterable(params)))
    _args = parser.parse_args([*params, *args])
    try:
        returncode = main(_args)
        return returncode or 0
    except SystemExit as e:
        return e.code


@contextmanager
def run_html(*args, **kwargs):
    with temp_dir() as path:
        run(*args, html=None, html_dir=path, **kwargs)
        with chdir(path):
            yield


@contextmanager
def redirect_streams():
    stdout, stderr = StringIO(), StringIO()
    with redirect_stderr(stderr), redirect_stdout(stdout):
        yield stdout, stderr


class CliTest(unittest.TestCase):
    ALL_FILES = [
        'example_pkg',
        'example_pkg/index.html',
        'example_pkg/module.m.html',
        'example_pkg/_private',
        'example_pkg/_private/index.html',
        'example_pkg/_private/module.m.html',
        'example_pkg/subpkg',
        'example_pkg/subpkg/_private.m.html',
        'example_pkg/subpkg/index.html',
        'example_pkg/subpkg2',
        'example_pkg/subpkg2/_private.m.html',
        'example_pkg/subpkg2/module.m.html',
        'example_pkg/subpkg2/index.html',
    ]
    PUBLIC_FILES = [f for f in ALL_FILES if '/_' not in f]

    def _basic_html_assertions(self, expected_files=PUBLIC_FILES):
        # Output directory tree layout is as expected
        files = glob('**', recursive=True)
        self.assertEqual(sorted(files), sorted(expected_files))

    def _check_files(self, include_patterns=(), exclude_patterns=(), file_pattern='**/*.html'):
        files = glob(file_pattern, recursive=True)
        assert files
        for file in files:
            with open(file) as f:
                contents = f.read()
                for pattern in include_patterns:
                    self.assertIn(pattern, contents)
                for pattern in exclude_patterns:
                    self.assertNotIn(pattern, contents)

    def test_html(self):
        include_patterns = [
            'CONST docstring',
            'var docstring',
            'foreign_var',
            'foreign var docstring',
            'A',
            'A.overridden docstring',
            'A.overridden_same_docstring docstring',
            'A.inherited',
            'B docstring',
            'B.overridden docstring',
            'builtins.int',
            'External: ',
            '>sys.version<',
            'B.CONST docstring',
            'B.var docstring',
            'b=1',
            '*args',
            '**kwargs',
            '__init__ docstring',
            'instance_var',
            'instance var docstring',
            'B.f docstring',
            'B.static docstring',
            'B.cls docstring',
            'B.p docstring',
            'B.C docstring',
            'B.overridden docstring',

            ' class="ident">static',
        ]
        exclude_patterns = [
            ' class="ident">_private',
            ' class="ident">_Private',
        ]
        package_files = {
            '': self.PUBLIC_FILES,
            '.subpkg2': [f for f in self.PUBLIC_FILES
                         if 'subpkg2' in f or f == EXAMPLE_MODULE],
            '._private': [f for f in self.ALL_FILES
                          if EXAMPLE_MODULE + '/_private' in f or f == EXAMPLE_MODULE],
        }
        for package, expected_files in package_files.items():
            with self.subTest(package=package):
                with run_html(EXAMPLE_MODULE + package):
                    self._basic_html_assertions(expected_files)
                    self._check_files(include_patterns, exclude_patterns)

        filenames_files = {
            ('module.py',): [EXAMPLE_MODULE, EXAMPLE_MODULE + '/module.m.html'],
            ('module.py', 'subpkg2'): [f for f in self.PUBLIC_FILES
                                       if 'module' in f or 'subpkg2' in f or f == EXAMPLE_MODULE],
        }
        with chdir(TESTS_BASEDIR):
            for filenames, expected_files in filenames_files.items():
                with self.subTest(filename=','.join(filenames)):
                    with run_html(*(os.path.join(EXAMPLE_MODULE, f) for f in filenames)):
                        self._basic_html_assertions(expected_files)
                        self._check_files(include_patterns, exclude_patterns)

    def test_html_multiple_files(self):
        with chdir(TESTS_BASEDIR):
            with run_html(EXAMPLE_MODULE + '/module.py', EXAMPLE_MODULE + '/subpkg2'):
                self._basic_html_assertions(
                    [f for f in self.PUBLIC_FILES
                     if 'module' in f or 'subpkg2' in f or f == EXAMPLE_MODULE])

    def test_html_identifier(self):
        for package in ('', '._private'):
            with self.subTest(package=package):
                with run_html(EXAMPLE_MODULE + package, filter='A', html_no_source=None):
                    self._check_files(['A'], ['CONST', 'B docstring'])

    def test_html_ref_links(self):
        with run_html(EXAMPLE_MODULE, html_no_source=None):
            self._check_files(
                file_pattern=EXAMPLE_MODULE + '/index.html',
                include_patterns=[
                    'href="#example_pkg.B">',
                    'href="#example_pkg.A">',
                ],
            )

    def test_html_no_source(self):
        with run_html(EXAMPLE_MODULE, html_no_source=None):
            self._basic_html_assertions()
            self._check_files(exclude_patterns=['class="source"', 'Hidden'])

    def test_overwrite(self):
        with run_html(EXAMPLE_MODULE):
            with redirect_streams() as (stdout, stderr):
                returncode = run(EXAMPLE_MODULE, _check=False, html=None)
                self.assertNotEqual(returncode, 0)
                self.assertNotEqual(stderr.getvalue(), '')

            with redirect_streams() as (stdout, stderr):
                returncode = run(EXAMPLE_MODULE, html=None, overwrite=None)
                self.assertEqual(returncode, 0)
                self.assertEqual(stderr.getvalue(), '')

    def test_external_links(self):
        with run_html(EXAMPLE_MODULE):
            self._basic_html_assertions()
            self._check_files(exclude_patterns=['<a href="/sys.version.ext"'])

        with run_html(EXAMPLE_MODULE, external_links=None):
            self._basic_html_assertions()
            self._check_files(['<a href="/sys.version.ext"'])

    def test_template_dir(self):
        old_tpl_dirs = pdoc.tpl_lookup.directories.copy()
        # Prevent loading incorrect template cached from prev runs
        pdoc.tpl_lookup._collection.clear()
        try:
            with run_html(EXAMPLE_MODULE, template_dir=TESTS_BASEDIR):
                self._basic_html_assertions()
                self._check_files(['FOOBAR', '/* Empty CSS */'], ['coding: utf-8'])
        finally:
            pdoc.tpl_lookup.directories = old_tpl_dirs
            pdoc.tpl_lookup._collection.clear()

    def test_link_prefix(self):
        with run_html(EXAMPLE_MODULE, link_prefix='/foobar/'):
            self._basic_html_assertions()
            self._check_files(['/foobar/' + EXAMPLE_MODULE])

    def test_text(self):
        include_patterns = [
            'CONST docstring',
            'var docstring',
            'foreign_var',
            'foreign var docstring',
            'A',
            'A.overridden docstring',
            'A.overridden_same_docstring docstring',
            'A.inherited',
            'B docstring',
            'B.overridden docstring',
            'builtins.int',
            'External: ',
            'sys.version',
            'B.CONST docstring',
            'B.var docstring',
            '__init__ docstring',
            'instance_var',
            'instance var docstring',
            'b=1',
            '*args',
            '**kwargs',
            'B.f docstring',
            'B.static docstring',
            'B.cls docstring',
            'B.p docstring',
            'C',
            'B.overridden docstring',
        ]
        exclude_patterns = [
            '_private',
            '_Private',
            'subprocess',
            'Hidden',
        ]

        with self.subTest(package=EXAMPLE_MODULE):
            with redirect_streams() as (stdout, _):
                run(EXAMPLE_MODULE)
                out = stdout.getvalue()

            header = 'Module {}\n{:-<{}}'.format(EXAMPLE_MODULE, '',
                                                 len('Module ') + len(EXAMPLE_MODULE))
            self.assertIn(header, out)
            for pattern in include_patterns:
                self.assertIn(pattern, out)
            for pattern in exclude_patterns:
                self.assertNotIn(pattern, out)

        with chdir(TESTS_BASEDIR):
            for files in (('module.py',),
                          ('module.py', 'subpkg2')):
                with self.subTest(filename=','.join(files)):
                    with redirect_streams() as (stdout, _):
                        run(*(os.path.join(EXAMPLE_MODULE, f) for f in files))
                        out = stdout.getvalue()
                    for f in files:
                        header = 'Module {}.{}'.format(EXAMPLE_MODULE, os.path.splitext(f)[0])
                        self.assertIn(header, out)

    def test_text_identifier(self):
        with redirect_streams() as (stdout, _):
            run(EXAMPLE_MODULE, filter='A')
            out = stdout.getvalue()
        self.assertIn('A', out)
        self.assertIn('Descendents\n    -----------\n    example_pkg.B', out)
        self.assertNotIn('CONST', out)
        self.assertNotIn('B docstring', out)


class ApiTest(unittest.TestCase):
    def test_module(self):
        modules = {
            EXAMPLE_MODULE: ('', ('module', 'subpkg', 'subpkg2')),
            os.path.join(EXAMPLE_MODULE, 'subpkg2'): ('.subpkg2', ('subpkg2.module',)),
        }
        with chdir(TESTS_BASEDIR):
            for module, (name_suffix, submodules) in modules.items():
                with self.subTest(module=module):
                    m = pdoc.Module(pdoc.import_module(module))
                    self.assertEqual(repr(m), "<Module '{}'>".format(m.obj.__name__))
                    self.assertEqual(m.name, EXAMPLE_MODULE + name_suffix)
                    self.assertEqual(sorted(m.name for m in m.submodules()),
                                     [EXAMPLE_MODULE + '.' + m for m in submodules])

    def test_import_filename(self):
        old_sys_path = sys.path.copy()
        sys.path.clear()
        with chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE)):
            pdoc.import_module('index')
        sys.path = old_sys_path

    def test_module_allsubmodules(self):
        m = pdoc.Module(pdoc.import_module(EXAMPLE_MODULE + '._private'))
        self.assertEqual(sorted(m.name for m in m.submodules()),
                         [EXAMPLE_MODULE + '._private.module'])

    def test_refname(self):
        mod = EXAMPLE_MODULE + '.' + 'subpkg'
        module = pdoc.Module(pdoc.import_module(mod))
        var = module.doc['var']
        cls = module.doc['B']
        nested_cls = cls.doc['C']
        cls_var = cls.doc['var']
        method = cls.doc['f']

        self.assertEqual(pdoc.External('foo').refname, 'foo')
        self.assertEqual(module.refname, mod)
        self.assertEqual(var.refname, mod + '.var')
        self.assertEqual(cls.refname, mod + '.B')
        self.assertEqual(nested_cls.refname, mod + '.B.C')
        self.assertEqual(cls_var.refname, mod + '.B.var')
        self.assertEqual(method.refname, mod + '.B.f')

        # Inherited method's refname points to class' implicit copy
        self.assertEqual(cls.doc['inherited'].refname, mod + '.B.inherited')

    def test_qualname(self):
        module = pdoc.Module(pdoc.import_module(EXAMPLE_MODULE))
        var = module.doc['var']
        cls = module.doc['B']
        nested_cls = cls.doc['C']
        cls_var = cls.doc['var']
        method = cls.doc['f']

        self.assertEqual(pdoc.External('foo').qualname, 'foo')
        self.assertEqual(module.qualname, EXAMPLE_MODULE)
        self.assertEqual(var.qualname, 'var')
        self.assertEqual(cls.qualname, 'B')
        self.assertEqual(nested_cls.qualname, 'B.C')
        self.assertEqual(cls_var.qualname, 'B.var')
        self.assertEqual(method.qualname, 'B.f')

    def test__pdoc__dict(self):
        module = pdoc.import_module(EXAMPLE_MODULE)
        old__pdoc__ = module.__pdoc__
        module.__pdoc__ = {'B': None}
        mod = pdoc.Module(module)
        self.assertIn('A', mod.doc)
        self.assertNotIn('B', mod.doc)
        module.__pdoc__ = old__pdoc__

    def test_find_ident(self):
        mod = pdoc.Module(pdoc.import_module(EXAMPLE_MODULE))
        self.assertIsInstance(mod.find_ident('subpkg'), pdoc.Module)
        mod = pdoc.Module(pdoc)
        self.assertIsInstance(mod.find_ident('subpkg'), pdoc.External)

    def test_inherits(self):
        module = pdoc.Module(pdoc.import_module(EXAMPLE_MODULE))
        a = module.doc['A']
        b = module.doc['B']
        self.assertEqual(b.doc['inherited'].inherits,
                         a.doc['inherited'])
        self.assertEqual(b.doc['overridden_same_docstring'].inherits,
                         a.doc['overridden_same_docstring'])
        self.assertEqual(b.doc['overridden'].inherits,
                         None)


class HttpTest(unittest.TestCase):
    @contextmanager
    def _timeout(self, secs):
        def _raise(*_):
            raise TimeoutError

        signal.signal(signal.SIGALRM, _raise)
        signal.alarm(secs)
        yield
        signal.alarm(0)

    def test_http(self):
        host, port = 'localhost', randint(9000, 12000)
        cmd = 'pdoc --http --http-host {} --http-port {} pdoc {}'.format(
            host, port, EXAMPLE_MODULE).split()

        with self._timeout(10):
            with subprocess.Popen(cmd, stderr=subprocess.PIPE) as proc:
                sleep(1)

                if proc.poll() is not None:
                    sys.stderr.write(proc.stderr.read().decode(sys.getdefaultencoding()))
                    raise AssertionError

                try:
                    url = 'http://{}:{}/'.format(host, port)
                    with self.subTest(url='/'):
                        with urlopen(url, timeout=3) as resp:
                            html = resp.read()
                            self.assertIn(b'Module pdoc provides types and functions', html)
                    with self.subTest(url='/' + EXAMPLE_MODULE):
                        with urlopen(url + 'pdoc', timeout=3) as resp:
                            html = resp.read()
                            self.assertIn(b'__pdoc__', html)
                finally:
                    proc.terminate()
                    proc.kill()


if __name__ == '__main__':
    unittest.main()
