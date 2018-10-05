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
        main(_args)
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

        with chdir(TESTS_BASEDIR):
            with self.subTest(filename='module.py'):
                with run_html(EXAMPLE_MODULE + '/module.py'):
                    self._basic_html_assertions(['__init__', '__init__/index.html'])
                    self._check_files(include_patterns, exclude_patterns)

    def test_html_identifier(self):
        for package in ('', '._private'):
            with self.subTest(package=package):
                with run_html(EXAMPLE_MODULE + package, 'A', html_no_source=None):
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

    def test_all_submodules(self):
        with run_html(EXAMPLE_MODULE, all_submodules=None):
            self._basic_html_assertions(expected_files=self.ALL_FILES)

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
        with redirect_streams() as (stdout, _):
            run(EXAMPLE_MODULE)
            out = stdout.getvalue()

        include_patterns = [
            'CONST docstring',
            'var docstring',
            'foreign_var',
            'foreign var docstring',
            'A',
            'A.overridden docstring',
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

        header = 'Module {}\n{:-<{}}'.format(EXAMPLE_MODULE, '',
                                             len('Module ') + len(EXAMPLE_MODULE))
        self.assertIn(header, out)
        for pattern in include_patterns:
            self.assertIn(pattern, out)
        for pattern in exclude_patterns:
            self.assertNotIn(pattern, out)

    def test_text_identifier(self):
        with redirect_streams() as (stdout, _):
            run(EXAMPLE_MODULE, 'A')
            out = stdout.getvalue()
        self.assertIn('A', out)
        self.assertIn('Descendents\n    -----------\n    example_pkg.B', out)
        self.assertNotIn('CONST', out)
        self.assertNotIn('B docstring', out)


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
        cmd = 'pdoc --http --http-host {} --http-port {}'.format(host, port).split()

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
