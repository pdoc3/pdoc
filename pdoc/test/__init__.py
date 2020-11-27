"""
Unit tests for pdoc package.
"""
import enum
import inspect
import os
import shutil
import signal
import subprocess
import sys
import typing
import threading
import unittest
import warnings
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from functools import wraps
from glob import glob
from io import StringIO
from itertools import chain
from random import randint
from tempfile import TemporaryDirectory
from time import sleep
from types import ModuleType
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pdoc
from pdoc import cli
from pdoc.html_helpers import (
    minify_css, minify_html, glimpse, to_html,
    ReferenceWarning, extract_toc, format_git_link,
)

TESTS_BASEDIR = os.path.abspath(os.path.dirname(__file__) or '.')
sys.path.insert(0, TESTS_BASEDIR)

EXAMPLE_MODULE = 'example_pkg'
EXAMPLE_PDOC_MODULE = pdoc.Module(EXAMPLE_MODULE, context=pdoc.Context())
PDOC_PDOC_MODULE = pdoc.Module(pdoc, context=pdoc.Context())

EMPTY_MODULE = ModuleType('empty')
EMPTY_MODULE.__pdoc__ = {}  # type: ignore
with warnings.catch_warnings(record=True):
    DUMMY_PDOC_MODULE = pdoc.Module(EMPTY_MODULE, context=pdoc.Context())

T = typing.TypeVar("T")


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
    params = list(filter(None, chain.from_iterable(params)))  # type: ignore
    _args = cli.parser.parse_args([*params, *args])           # type: ignore
    try:
        returncode = cli.main(_args)
        return returncode or 0
    except SystemExit as e:
        return e.code


@contextmanager
def run_html(*args, **kwargs):
    with temp_dir() as path, \
            redirect_streams():
        run(*args, html=None, output_dir=path, **kwargs)
        with chdir(path):
            yield


@contextmanager
def redirect_streams():
    stdout, stderr = StringIO(), StringIO()
    with redirect_stderr(stderr), redirect_stdout(stdout):
        yield stdout, stderr


def ignore_warnings(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            func(*args, **kwargs)
    return wrapper


class CliTest(unittest.TestCase):
    """
    Command-line interface unit tests.
    """
    ALL_FILES = [
        'example_pkg',
        'example_pkg/index.html',
        'example_pkg/index.m.html',
        'example_pkg/module.html',
        'example_pkg/_private',
        'example_pkg/_private/index.html',
        'example_pkg/_private/module.html',
        'example_pkg/subpkg',
        'example_pkg/subpkg/_private.html',
        'example_pkg/subpkg/index.html',
        'example_pkg/subpkg2',
        'example_pkg/subpkg2/_private.html',
        'example_pkg/subpkg2/module.html',
        'example_pkg/subpkg2/index.html',
    ]
    PUBLIC_FILES = [f for f in ALL_FILES if '/_' not in f]

    if os.name == 'nt':
        ALL_FILES = [i.replace('/', '\\') for i in ALL_FILES]
        PUBLIC_FILES = [i.replace('/', '\\') for i in PUBLIC_FILES]

    def setUp(self):
        pdoc.reset()

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
            'a=&lt;object',
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
            'External refs: ',
            '>sys.version<',
            'B.CONST docstring',
            'B.var docstring',
            'b=1',
            '*args',
            '**kwargs',
            'x, y, z, w',
            'instance_var',
            'instance var docstring',
            'B.f docstring',
            'B.static docstring',
            'B.cls docstring',
            'B.p docstring',
            'B.C docstring',
            'B.overridden docstring',

            '<code>__init__</code> docstring',
            ' class="ident">static',
        ]
        exclude_patterns = [
            '<object ',
            ' class="ident">_private',
            ' class="ident">_Private',
            'non_callable_routine',
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
                with run_html(EXAMPLE_MODULE + package,
                              '--config', 'show_type_annotations=False',
                              config='show_source_code=False'):
                    self._basic_html_assertions(expected_files)
                    self._check_files(include_patterns, exclude_patterns)

        filenames_files = {
            ('module.py',): ['module.html'],
            ('module.py', 'subpkg2'): ['module.html', 'subpkg2',
                                       'subpkg2/index.html', 'subpkg2/module.html'],
        }
        with chdir(TESTS_BASEDIR):
            for filenames, expected_files in filenames_files.items():
                with self.subTest(filename=','.join(filenames)):
                    with run_html(*(os.path.join(EXAMPLE_MODULE, f) for f in filenames),
                                  '--config', 'show_type_annotations=False',
                                  config='show_source_code=False'):
                        self._basic_html_assertions(expected_files)
                        self._check_files(include_patterns, exclude_patterns)

    def test_html_multiple_files(self):
        with chdir(TESTS_BASEDIR):
            with run_html(EXAMPLE_MODULE + '/module.py', EXAMPLE_MODULE + '/subpkg2'):
                self._basic_html_assertions(
                    ['module.html', 'subpkg2', 'subpkg2/index.html', 'subpkg2/module.html'])

    def test_html_identifier(self):
        for package in ('', '._private'):
            with self.subTest(package=package), \
                    self.assertWarns(UserWarning) as cm:
                with run_html(EXAMPLE_MODULE + package, filter='A',
                              config='show_source_code=False'):
                    self._check_files(['A'], ['CONST', 'B docstring'])
        self.assertIn('__pdoc__', cm.warning.args[0])

    def test_html_ref_links(self):
        with run_html(EXAMPLE_MODULE, config='show_source_code=False'):
            self._check_files(
                file_pattern=EXAMPLE_MODULE + '/index.html',
                include_patterns=[
                    'href="#example_pkg.B">',
                    'href="#example_pkg.A">',
                ],
            )

    def test_docformat(self):
        with self.assertWarns(UserWarning) as cm,\
                run_html(EXAMPLE_MODULE, config='docformat="restructuredtext"'):
            self._basic_html_assertions()
        self.assertIn('numpy', cm.warning.args[0])

    def test_html_no_source(self):
        with self.assertWarns(DeprecationWarning),\
                run_html(EXAMPLE_MODULE, html_no_source=None):
            self._basic_html_assertions()
            self._check_files(exclude_patterns=['class="source"', 'Hidden'])

    def test_google_search_query(self):
        with run_html(EXAMPLE_MODULE, config='google_search_query="anything"'):
            self._basic_html_assertions()
            self._check_files(include_patterns=['class="gcse-search"'])

    def test_lunr_search(self):
        with run_html(EXAMPLE_MODULE, config='lunr_search={"fuzziness": 1}'):
            files = self.PUBLIC_FILES + ["doc-search.html", "index.js"]
            self._basic_html_assertions(expected_files=files)
            self._check_files(exclude_patterns=['class="gcse-search"'])
            self._check_files(include_patterns=['URLS=[\n"example_pkg/index.html",\n"example_pkg/'],
                              file_pattern='index.js')
            self._check_files(include_patterns=["'../doc-search.html#'"],
                              file_pattern='example_pkg/index.html')
            self._check_files(include_patterns=["'../doc-search.html#'"],
                              file_pattern='example_pkg/module.html')
            self._check_files(include_patterns=["'../../doc-search.html#'"],
                              file_pattern='example_pkg/subpkg/index.html')

    def test_force(self):
        with run_html(EXAMPLE_MODULE):
            with redirect_streams() as (stdout, stderr):
                returncode = run(EXAMPLE_MODULE, _check=False, html=None, output_dir=os.getcwd())
                self.assertNotEqual(returncode, 0)
                self.assertNotEqual(stderr.getvalue(), '')

            with redirect_streams() as (stdout, stderr):
                returncode = run(EXAMPLE_MODULE, html=None, force=None, output_dir=os.getcwd())
                self.assertEqual(returncode, 0)
                self.assertEqual(stderr.getvalue(), '')

    def test_external_links(self):
        with run_html(EXAMPLE_MODULE):
            self._basic_html_assertions()
            self._check_files(exclude_patterns=['<a href="/sys.version.ext"'])

        with self.assertWarns(DeprecationWarning),\
                run_html(EXAMPLE_MODULE, external_links=None):
            self._basic_html_assertions()
            self._check_files(['<a title="sys.version" href="/sys.version.ext"'])

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
        with self.assertWarns(DeprecationWarning),\
                run_html(EXAMPLE_MODULE, link_prefix='/foobar/'):
            self._basic_html_assertions()
            self._check_files(['/foobar/' + EXAMPLE_MODULE])

    def test_text(self):
        include_patterns = [
            'object_as_arg_default(*args, a=<object ',
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
            'External refs: ',
            'sys.version',
            'B.CONST docstring',
            'B.var docstring',
            'x, y, z, w',
            '`__init__` docstring',
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
            'non_callable_routine',
        ]

        with self.subTest(package=EXAMPLE_MODULE):
            with redirect_streams() as (stdout, _):
                run(EXAMPLE_MODULE, config='show_type_annotations=False')
                out = stdout.getvalue()

            header = 'Module {}\n{:=<{}}'.format(EXAMPLE_MODULE, '',
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
                        header = 'Module {}\n'.format(os.path.splitext(f)[0])
                        self.assertIn(header, out)

    def test_text_identifier(self):
        with redirect_streams() as (stdout, _):
            run(EXAMPLE_MODULE, filter='A')
            out = stdout.getvalue()
        self.assertIn('A', out)
        self.assertIn('### Descendants\n\n    * example_pkg.B', out)
        self.assertNotIn('CONST', out)
        self.assertNotIn('B docstring', out)

    def test_pdf(self):
        with redirect_streams() as (stdout, stderr):
            run('pdoc', pdf=None)
            out = stdout.getvalue()
            err = stderr.getvalue()
        self.assertIn('pdoc3.github.io', out)
        self.assertIn('pandoc', err)

        pdoc_Doc_params = str(inspect.signature(pdoc.Doc.__init__)).replace('self, ', '')
        self.assertIn(pdoc_Doc_params.replace(' ', ''),
                      out.replace('>', '').replace('\n', '').replace(' ', ''))

    @unittest.skipUnless('PDOC_TEST_PANDOC' in os.environ, 'PDOC_TEST_PANDOC not set/requested')
    def test_pdf_pandoc(self):
        with temp_dir() as path, \
                chdir(path), \
                redirect_streams() as (stdout, _), \
                open('pdf.md', 'w') as f:
            run('pdoc', pdf=None)
            f.write(stdout.getvalue())
            subprocess.run(pdoc.cli._PANDOC_COMMAND, shell=True, check=True)
            self.assertTrue(os.path.exists('pdf.pdf'))

    def test_config(self):
        with run_html(EXAMPLE_MODULE, config='link_prefix="/foobar/"'):
            self._basic_html_assertions()
            self._check_files(['/foobar/' + EXAMPLE_MODULE])

    def test_output_text(self):
        with temp_dir() as path, \
                redirect_streams():
            run(EXAMPLE_MODULE, output_dir=path)
            with chdir(path):
                self._basic_html_assertions([file.replace('.html', '.md')
                                             for file in self.PUBLIC_FILES])

    def test_google_analytics(self):
        expected = ['google-analytics.com']
        with run_html(EXAMPLE_MODULE):
            self._check_files((), exclude_patterns=expected)
        with run_html(EXAMPLE_MODULE, config='google_analytics="UA-xxxxxx-y"'):
            self._check_files(expected)

    def test_relative_dir_path(self):
        with chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE)):
            with run_html('.'):
                self._check_files(())

    def test_skip_errors(self):
        with chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE, '_skip_errors')),\
                redirect_streams(),\
                self.assertWarns(pdoc.Module.ImportWarning) as cm:
            run('.', skip_errors=None)
        self.assertIn('ZeroDivision', cm.warning.args[0])

    @unittest.skipIf(sys.version_info < (3, 7), '__future__.annotations unsupported in <Py3.7')
    def test_resolve_typing_forwardrefs(self):
        # GH-245
        with chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE, '_resolve_typing_forwardrefs')):
            with redirect_streams() as (out, _err):
                run('postponed')
            out = out.getvalue()
            self.assertIn('bar', out)
            self.assertIn('baz', out)
            self.assertIn('dt', out)
            self.assertIn('datetime', out)

            with redirect_streams() as (out, _err):
                run('evaluated')
            out = out.getvalue()
            self.assertIn('Set[Bar]', out)


class ApiTest(unittest.TestCase):
    """
    Programmatic/API unit tests.
    """
    def setUp(self):
        pdoc.reset()

    def test_module(self):
        modules = {
            EXAMPLE_MODULE: ('', ('index', 'module', 'subpkg', 'subpkg2')),
            EXAMPLE_MODULE + '.subpkg2': ('.subpkg2', ('subpkg2.module',)),
        }
        with chdir(TESTS_BASEDIR):
            for module, (name_suffix, submodules) in modules.items():
                with self.subTest(module=module):
                    m = pdoc.Module(module)
                    self.assertEqual(repr(m), "<Module '{}'>".format(m.obj.__name__))
                    self.assertEqual(m.name, EXAMPLE_MODULE + name_suffix)
                    self.assertEqual(sorted(m.name for m in m.submodules()),
                                     [EXAMPLE_MODULE + '.' + m for m in submodules])

    def test_Module_find_class(self):
        class A:
            pass

        mod = PDOC_PDOC_MODULE
        self.assertIsInstance(mod.find_class(pdoc.Doc), pdoc.Class)
        self.assertIsInstance(mod.find_class(A), pdoc.External)

    def test_import_filename(self):
        with patch.object(sys, 'path', ['']), \
                chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE)):
            pdoc.import_module('index')

    def test_imported_once(self):
        with chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE)):
            pdoc.import_module('_imported_once.py')

    def test_namespace(self):
        # Test the three namespace types
        # https://packaging.python.org/guides/packaging-namespace-packages/#creating-a-namespace-package
        for i in range(1, 4):
            path = os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE, '_namespace', str(i))
            with patch.object(sys, 'path', [os.path.join(path, 'a'),
                                            os.path.join(path, 'b')]):
                mod = pdoc.Module('a.main')
                self.assertIn('D', mod.doc)

    def test_module_allsubmodules(self):
        m = pdoc.Module(EXAMPLE_MODULE + '._private')
        self.assertEqual(sorted(m.name for m in m.submodules()),
                         [EXAMPLE_MODULE + '._private.module'])

    def test_instance_var(self):
        mod = EXAMPLE_PDOC_MODULE
        var = mod.doc['B'].doc['instance_var']
        self.assertTrue(var.instance_var)

    def test_readonly_value_descriptors(self):
        pdoc.reset()
        mod = pdoc.Module(pdoc.import_module(EXAMPLE_MODULE))
        var = mod.doc['B'].doc['ro_value_descriptor']
        self.assertIsInstance(var, pdoc.Variable)
        self.assertTrue(var.instance_var)
        self.assertEqual(var.docstring, """ro_value_descriptor docstring""")
        self.assertTrue(var.source)

        var = mod.doc['B'].doc['ro_value_descriptor_no_doc']
        self.assertIsInstance(var, pdoc.Variable)
        self.assertTrue(var.instance_var)
        self.assertEqual(var.docstring, """Read-only value descriptor""")
        self.assertTrue(var.source)

    def test_class_variables_docstring_not_from_obj(self):
        class C:
            vars_dont = 0
            but_clss_have_doc = int

        doc = pdoc.Class('C', DUMMY_PDOC_MODULE, C)
        self.assertEqual(doc.doc['vars_dont'].docstring, '')
        self.assertIn('integer', doc.doc['but_clss_have_doc'].docstring)

    def test_builtin_methoddescriptors(self):
        import parser
        with self.assertWarns(UserWarning):
            c = pdoc.Class('STType', pdoc.Module(parser), parser.STType)
        self.assertIsInstance(c.doc['compile'], pdoc.Function)

    def test_refname(self):
        mod = EXAMPLE_MODULE + '.' + 'subpkg'
        module = pdoc.Module(mod)
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
        pdoc.link_inheritance()
        self.assertEqual(cls.doc['inherited'].refname, mod + '.B.inherited')

    def test_qualname(self):
        module = EXAMPLE_PDOC_MODULE
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
        with patch.object(module, '__pdoc__', {'B': False}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('A', mod.doc)
            self.assertNotIn('B', mod.doc)

        with patch.object(module, '__pdoc__', {'B.f': False}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('B', mod.doc)
            self.assertNotIn('f', mod.doc['B'].doc)
            self.assertIsInstance(mod.find_ident('B.f'), pdoc.External)

        # GH-125: https://github.com/pdoc3/pdoc/issues/125
        with patch.object(module, '__pdoc__', {'B.inherited': False}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertNotIn('inherited', mod.doc['B'].doc)

        # GH-99: https://github.com/pdoc3/pdoc/issues/99
        module = pdoc.import_module(EXAMPLE_MODULE + '._exclude_dir')
        with patch.object(module, '__pdoc__', {'downloaded_modules': False}, create=True):
            mod = pdoc.Module(module)
            # GH-206: https://github.com/pdoc3/pdoc/issues/206
            with warnings.catch_warnings(record=True) as cm:
                pdoc.link_inheritance()
            self.assertEqual(cm, [])
            self.assertNotIn('downloaded_modules', mod.doc)

    @ignore_warnings
    def test_dont_touch__pdoc__blacklisted(self):
        class Bomb:
            def __getattribute__(self, item):
                raise RuntimeError

        class D:
            x = Bomb()
            """doc"""
            __qualname__ = 'D'

        module = EMPTY_MODULE
        D.__module__ = module.__name__  # Need to match is_from_this_module check
        with patch.object(module, 'x', Bomb(), create=True), \
             patch.object(module, '__pdoc__', {'x': False}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertNotIn('x', mod.doc)
        with patch.object(module, 'D', D, create=True), \
             patch.object(module, '__pdoc__', {'D.x': False}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertNotIn('x', mod.doc['D'].doc)

    def test__pdoc__invalid_value(self):
        module = pdoc.import_module(EXAMPLE_MODULE)
        with patch.object(module, '__pdoc__', {'B': 1}), \
                self.assertRaises(ValueError):
            pdoc.Module(module)
            pdoc.link_inheritance()

    def test__pdoc__whitelist(self):
        module = pdoc.import_module(EXAMPLE_MODULE)
        mod = pdoc.Module(module)
        pdoc.link_inheritance()
        self.assertNotIn('__call__', mod.doc['A'].doc)
        self.assertNotIn('_private_function', mod.doc)

        # Override docstring string
        docstring = "Overwrite private function doc"
        with patch.object(module, '__pdoc__', {'A.__call__': docstring}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertEqual(mod.doc['A'].doc['__call__'].docstring, docstring)

        # Module-relative
        with patch.object(module, '__pdoc__', {'_private_function': True}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('Private function', mod.doc['_private_function'].docstring)
            self.assertNotIn('_private_function', mod.doc["subpkg"].doc)

        # Defined in example_pkg, referring to a member of its submodule
        with patch.object(module, '__pdoc__', {'subpkg.A.__call__': True}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('A.__call__', mod.doc['subpkg'].doc['A'].doc['__call__'].docstring)

        # Using full refname
        with patch.object(module, '__pdoc__', {'example_pkg.subpkg.A.__call__': True}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('A.__call__', mod.doc['subpkg'].doc['A'].doc['__call__'].docstring)

        # Entire module, absolute refname
        with patch.object(module, '__pdoc__', {'example_pkg._private': True}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('module', mod.doc['_private'].doc)
            self.assertNotIn('_private', mod.doc['_private'].doc)
            self.assertNotIn('__call__', mod.doc['_private'].doc['module'].doc)

        # Entire module, relative
        with patch.object(module, '__pdoc__', {'_private': True}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('_private', mod.doc)
            self.assertNotIn('_private', mod.doc['_private'].doc)
            self.assertNotIn('__call__', mod.doc['_private'].doc['module'].doc)

        # Private instance variables
        with patch.object(module, '__pdoc__', {'B._private_instance_var': True}):
            mod = pdoc.Module(module)
            pdoc.link_inheritance()
            self.assertIn('should be private', mod.doc['B'].doc['_private_instance_var'].docstring)

    def test__all__(self):
        module = pdoc.import_module(EXAMPLE_MODULE + '.index')
        with patch.object(module, '__all__', ['B'], create=True):
            mod = pdoc.Module(module)
            with self.assertWarns(UserWarning):  # Only B is used but __pdoc__ contains others
                pdoc.link_inheritance()
            self.assertEqual(list(mod.doc.keys()), ['B'])

    def test_find_ident(self):
        mod = pdoc.Module(EXAMPLE_MODULE)
        self.assertIsInstance(mod.find_ident('subpkg'), pdoc.Module)
        mod = pdoc.Module(pdoc)
        self.assertIsInstance(mod.find_ident('subpkg'), pdoc.External)

        self.assertIsInstance(mod.find_ident(EXAMPLE_MODULE + '.subpkg'), pdoc.Module)

        nonexistent = 'foo()'
        result = mod.find_ident(nonexistent)
        self.assertIsInstance(result, pdoc.External)
        self.assertEqual(result.name, nonexistent)

        # Ref by class __init__
        self.assertIs(mod.find_ident('pdoc.Doc.__init__').obj, pdoc.Doc)

    def test_inherits(self):
        module = pdoc.Module(EXAMPLE_MODULE)
        pdoc.link_inheritance()

        a = module.doc['A']
        b = module.doc['B']
        self.assertEqual(b.doc['inherited'].inherits,
                         a.doc['inherited'])
        self.assertEqual(b.doc['overridden_same_docstring'].inherits,
                         a.doc['overridden_same_docstring'])
        self.assertEqual(b.doc['overridden'].inherits,
                         None)

        c = module.doc['C']
        d = module.doc['D']
        self.assertEqual(d.doc['overridden'].inherits, c.doc['overridden'])
        self.assertEqual(c.doc['overridden'].inherits, b.doc['overridden'])

    def test_inherited_members(self):
        mod = pdoc.Module(EXAMPLE_MODULE)
        pdoc.link_inheritance()
        a = mod.doc['A']
        b = mod.doc['B']
        self.assertEqual(b.inherited_members(), [(a, [a.doc['inherited'],
                                                      a.doc['overridden_same_docstring']])])
        self.assertEqual(a.inherited_members(), [])

    @ignore_warnings
    def test_subclasses(self):
        class A:
            pass

        class B(type):
            pass

        class C(A):
            pass

        class D(B):
            pass

        class G(C):
            pass

        class F(C):
            pass

        class E(C):
            pass

        mod = DUMMY_PDOC_MODULE
        self.assertEqual([x.refname for x in pdoc.Class('A', mod, A).subclasses()],
                         [mod.find_class(C).refname])
        self.assertEqual([x.refname for x in pdoc.Class('B', mod, B).subclasses()],
                         [mod.find_class(D).refname])
        self.assertEqual([x.refname for x in pdoc.Class('C', mod, C).subclasses()],
                         [mod.find_class(x).refname for x in (E, F, G)])

    def test_link_inheritance(self):
        mod = pdoc.Module(EXAMPLE_MODULE)
        with warnings.catch_warnings(record=True) as w:
            pdoc.link_inheritance()
            pdoc.link_inheritance()
        self.assertFalse(w)

        mod._is_inheritance_linked = False
        with self.assertWarns(UserWarning):
            pdoc.link_inheritance()

        # Test inheritance across modules
        pdoc.reset()
        mod = pdoc.Module(EXAMPLE_MODULE + '._test_linking')
        pdoc.link_inheritance()
        a = mod.doc['a'].doc['A']
        b = mod.doc['b'].doc['B']
        c = mod.doc['b'].doc['c'].doc['C']
        self.assertEqual(b.doc['a'].inherits, a.doc['a'])
        self.assertEqual(b.doc['c'].inherits, c.doc['c'])
        # While classes do inherit from superclasses, they just shouldn't always
        # say so, because public classes do want to be exposed and linked to
        self.assertNotEqual(b.inherits, a)

    def test_context(self):
        context = {}
        pdoc.Module(pdoc, context=context)
        self.assertIn('pdoc', context)
        self.assertIn('pdoc.cli', context)
        self.assertIn('pdoc.cli.main', context)
        self.assertIn('pdoc.Module', context)
        self.assertIsInstance(context['pdoc'], pdoc.Module)
        self.assertIsInstance(context['pdoc.cli'], pdoc.Module)
        self.assertIsInstance(context['pdoc.cli.main'], pdoc.Function)
        self.assertIsInstance(context['pdoc.Module'], pdoc.Class)

        module = pdoc.Module(pdoc)
        self.assertIsInstance(module.find_ident('pdoc.Module'), pdoc.Class)
        pdoc.reset()
        self.assertIsInstance(module.find_ident('pdoc.Module'), pdoc.External)

    def test_Function_params(self):
        mod = PDOC_PDOC_MODULE
        func = pdoc.Function('f', mod,
                             lambda a, _a, _b=None: None)
        self.assertEqual(func.params(), ['a', '_a'])

        func = pdoc.Function('f', mod,
                             lambda _ok, a, _a, *args, _b=None, c=None, _d=None: None)
        self.assertEqual(func.params(), ['_ok', 'a', '_a', '*args', 'c=None'])

        func = pdoc.Function('f', mod,
                             lambda a, b, *, _c=1: None)
        self.assertEqual(func.params(), ['a', 'b'])

        func = pdoc.Function('f', mod,
                             lambda a, *, b, c: None)
        self.assertEqual(func.params(), ['a', '*', 'b', 'c'])

        func = pdoc.Function('f', mod,
                             lambda a=os.environ, b=sys.stdout: None)
        self.assertEqual(func.params(), ['a=os.environ', 'b=sys.stdout'])

        class Foo(enum.Enum):
            a, b = 1, 2
        func = pdoc.Function('f', mod, lambda a=Foo.a: None)
        self.assertEqual(func.params(), ['a=Foo.a'])

        func = pdoc.Function('f', mod, lambda a=object(): None)
        self.assertEqual(func.params(), ['a=<object object>'])

        func = pdoc.Function('f', mod, lambda a=object(): None)
        self.assertEqual(func.params(link=lambda x: ''), ['a=&lt;object object&gt;'])

        # typed
        def f(a: int, *b, c: typing.List[pdoc.Doc] = []): pass
        func = pdoc.Function('f', mod, f)
        self.assertEqual(func.params(), ['a', '*b', "c=[]"])
        self.assertEqual(func.params(annotate=True),
                         ['a:\N{NBSP}int', '*b', "c:\N{NBSP}List[pdoc.Doc]\N{NBSP}=\N{NBSP}[]"])

        # typed, linked
        def link(dobj):
            return '<a href="{}">{}</a>'.format(dobj.url(relative_to=mod), dobj.qualname)

        self.assertEqual(func.params(annotate=True, link=link),
                         ['a:\N{NBSP}int', '*b',
                          "c:\N{NBSP}List[<a href=\"#pdoc.Doc\">Doc</a>]\N{NBSP}=\N{NBSP}[]"])

        # typed, linked, GH-311
        def f(a: typing.Dict[str, pdoc.Doc]): pass

        func = pdoc.Function('f', mod, f)
        self.assertEqual(func.params(annotate=True, link=link),
                         ["a:\N{NBSP}Dict[str,\N{NBSP}<a href=\"#pdoc.Doc\">Doc</a>]"])

        # shadowed name
        def f(pdoc: int): pass
        func = pdoc.Function('f', mod, f)
        self.assertEqual(func.params(annotate=True, link=link), ['pdoc:\N{NBSP}int'])

        def bug130_str_annotation(a: "str"):
            return

        self.assertEqual(pdoc.Function('bug130', mod, bug130_str_annotation).params(annotate=True),
                         ['a:\N{NBSP}str'])

        # typed, NewType
        CustomType = typing.NewType('CustomType', bool)

        def bug253_newtype_annotation(a: CustomType):
            return

        self.assertEqual(
            pdoc.Function('bug253', mod, bug253_newtype_annotation).params(annotate=True),
            ['a:\N{NBSP}CustomType'])

        # builtin callables with signatures in docstrings
        from itertools import repeat
        self.assertEqual(pdoc.Function('repeat', mod, repeat).params(), ['object', 'times'])
        self.assertEqual(pdoc.Function('slice', mod, slice).params(), ['start', 'stop', 'step'])

        class get_sample(repeat):
            """ get_sample(self: pdoc.int, pos: int) -> Tuple[int, float] """
        self.assertEqual(pdoc.Function('get_sample', mod, get_sample).params(annotate=True),
                         ['self:\xa0int', 'pos:\xa0int'])
        self.assertEqual(pdoc.Function('get_sample', mod, get_sample).return_annotation(),
                         'Tuple[int,\xa0float]')

    @unittest.skipIf(sys.version_info < (3, 8), "positional-only arguments unsupported in < py3.8")
    def test_test_Function_params_python38_specific(self):
        mod = DUMMY_PDOC_MODULE
        func = pdoc.Function('f', mod, eval("lambda a, /, b: None"))
        self.assertEqual(func.params(), ['a', '/', 'b'])

        func = pdoc.Function('f', mod, eval("lambda a, /: None"))
        self.assertEqual(func.params(), ['a', '/'])

    def test_Function_return_annotation(self):
        def f() -> typing.List[typing.Union[str, pdoc.Doc]]: pass
        func = pdoc.Function('f', DUMMY_PDOC_MODULE, f)
        self.assertEqual(func.return_annotation(), 'List[Union[str,\N{NBSP}pdoc.Doc]]')

    @ignore_warnings
    def test_Variable_type_annotation(self):
        class Foobar:
            @property
            def prop(self) -> typing.Optional[int]:
                pass

        mod = DUMMY_PDOC_MODULE
        cls = pdoc.Class('Foobar', mod, Foobar)
        self.assertEqual(cls.doc['prop'].type_annotation(), 'Union[int,\N{NBSP}NoneType]')

    @ignore_warnings
    @unittest.skipIf(sys.version_info < (3, 6), 'variable annotation unsupported in <Py3.6')
    def test_Variable_type_annotation_py36plus(self):
        with temp_dir() as path:
            filename = os.path.join(path, 'module36syntax.py')
            with open(filename, 'w') as f:
                f.write('''
from typing import overload

var: str = 'x'
"""dummy"""

class Foo:
    var: int = 3
    """dummy"""

    @overload
    def __init__(self, var2: float):
        pass

    def __init__(self, var2):
        self.var2: float = float(var2)
        """dummy2"""
                ''')
            mod = pdoc.Module(pdoc.import_module(filename))
            self.assertEqual(mod.doc['var'].type_annotation(), 'str')
            self.assertEqual(mod.doc['Foo'].doc['var'].type_annotation(), 'int')
            self.assertIsInstance(mod.doc['Foo'].doc['var2'], pdoc.Variable)
            self.assertEqual(mod.doc['Foo'].doc['var2'].type_annotation(), '')  # Won't fix
            self.assertEqual(mod.doc['Foo'].doc['var2'].docstring, 'dummy2')

            self.assertIn('var: str', mod.text())
            self.assertIn('var: int', mod.text())

    @ignore_warnings
    def test_Class_docstring(self):
        class A:
            """foo"""

        class B:
            def __init__(self):
                """foo"""

        class C:
            """foo"""
            def __init__(self):
                """bar"""

        class D(C):
            """baz"""

        class E(C):
            def __init__(self):
                """baz"""

        class F(typing.Generic[T]):
            """baz"""
            def __init__(self):
                """bar"""

        class G(F[int]):
            """foo"""

        mod = DUMMY_PDOC_MODULE
        self.assertEqual(pdoc.Class('A', mod, A).docstring, """foo""")
        self.assertEqual(pdoc.Class('B', mod, B).docstring, """foo""")
        self.assertEqual(pdoc.Class('C', mod, C).docstring, """foo\n\nbar""")
        self.assertEqual(pdoc.Class('D', mod, D).docstring, """baz\n\nbar""")
        self.assertEqual(pdoc.Class('E', mod, E).docstring, """foo\n\nbaz""")
        self.assertEqual(pdoc.Class('F', mod, F).docstring, """baz\n\nbar""")
        self.assertEqual(pdoc.Class('G', mod, G).docstring, """foo\n\nbar""")

    @ignore_warnings
    def test_Class_params(self):
        class C:
            def __init__(self, x):
                pass

        mod = DUMMY_PDOC_MODULE
        self.assertEqual(pdoc.Class('C', mod, C).params(), ['x'])
        with patch.dict(mod.obj.__pdoc__, {'C.__init__': False}):
            self.assertEqual(pdoc.Class('C', mod, C).params(), [])

        # test case for https://github.com/pdoc3/pdoc/issues/124
        class C2:
            __signature__ = inspect.signature(lambda a, b, c=None, *, d=1, e: None)

        self.assertEqual(pdoc.Class('C2', mod, C2).params(), ['a', 'b', 'c=None', '*', 'd=1', 'e'])

        class G(typing.Generic[T]):
            def __init__(self, a, b, c=100):
                pass

        self.assertEqual(pdoc.Class('G', mod, G).params(), ['a', 'b', 'c=100'])

        class G2(typing.Generic[T]):
            pass

        self.assertEqual(pdoc.Class('G2', mod, G2).params(), ['*args', '**kwds'])

    def test_url(self):
        mod = pdoc.Module(EXAMPLE_MODULE)
        pdoc.link_inheritance()

        c = mod.doc['D']
        self.assertEqual(c.url(), 'example_pkg/index.html#example_pkg.D')
        self.assertEqual(c.url(link_prefix='/'), '/example_pkg/index.html#example_pkg.D')
        self.assertEqual(c.url(relative_to=c.module), '#example_pkg.D')
        self.assertEqual(c.url(top_ancestor=True), c.url())  # Public classes do link to themselves

        f = c.doc['overridden']
        self.assertEqual(f.url(), 'example_pkg/index.html#example_pkg.D.overridden')
        self.assertEqual(f.url(link_prefix='/'), '/example_pkg/index.html#example_pkg.D.overridden')
        self.assertEqual(f.url(relative_to=c.module), '#example_pkg.D.overridden')
        self.assertEqual(f.url(top_ancestor=1), 'example_pkg/index.html#example_pkg.B.overridden')

    @unittest.skipIf(sys.version_info < (3, 6), reason="only deterministic on CPython 3.6+")
    def test_sorting(self):
        module = EXAMPLE_PDOC_MODULE

        sorted_variables = module.variables()
        unsorted_variables = module.variables(sort=False)
        self.assertNotEqual(sorted_variables, unsorted_variables)
        self.assertEqual(sorted_variables, sorted(unsorted_variables))

        sorted_functions = module.functions()
        unsorted_functions = module.functions(sort=False)
        self.assertNotEqual(sorted_functions, unsorted_functions)
        self.assertEqual(sorted_functions, sorted(unsorted_functions))

        sorted_classes = module.classes()
        unsorted_classes = module.classes(sort=False)
        self.assertNotEqual(sorted_classes, unsorted_classes)
        self.assertEqual(sorted_classes, sorted(unsorted_classes))

        cls = module.doc["Docformats"]

        sorted_methods = cls.methods()
        unsorted_methods = cls.methods(sort=False)
        self.assertNotEqual(sorted_methods, unsorted_methods)
        self.assertEqual(sorted_methods, sorted(unsorted_methods))

    def test_module_init(self):
        mod = pdoc.Module('pdoc.__init__')
        self.assertEqual(mod.name, 'pdoc')
        self.assertIn('Module', mod.doc)

    @ignore_warnings
    @unittest.skipIf(sys.version_info < (3, 6), 'variable type annotation unsupported in <Py3.6')
    def test_class_members(self):
        module = DUMMY_PDOC_MODULE

        # GH-200
        from enum import Enum

        class Tag(Enum):
            Char = 1

            def func(self):
                return self

        cls = pdoc.Class('Tag', module, Tag)
        self.assertIsInstance(cls.doc['Char'], pdoc.Variable)
        self.assertIsInstance(cls.doc['func'], pdoc.Function)

        # GH-210, GH-212
        my_locals = {}
        exec('class Employee:\n name: str', my_locals)
        cls = pdoc.Class('Employee', module, my_locals['Employee'])
        self.assertIsInstance(cls.doc['name'], pdoc.Variable)
        self.assertEqual(cls.doc['name'].type_annotation(), 'str')


class HtmlHelpersTest(unittest.TestCase):
    """
    Unit tests for helper functions for producing HTML.
    """

    def test_minify_css(self):
        css = 'a { color: white; } /*comment*/ b {;}'
        minified = minify_css(css)
        self.assertNotIn(' ', minified)
        self.assertNotIn(';}', minified)
        self.assertNotIn('*', minified)

    def test_minify_html(self):
        html = '  <p>   a   </p>    <pre>    a\n    b</pre>    c   \n    d   '
        expected = '\n<p>\na\n</p>\n<pre>    a\n    b</pre>\nc\nd\n'
        minified = minify_html(html)
        self.assertEqual(minified, expected)

    def test_glimpse(self):
        text = 'foo bar\n\nbaz'
        self.assertEqual(glimpse(text), 'foo bar …')
        self.assertEqual(glimpse(text, max_length=8, paragraph=False), 'foo …')
        self.assertEqual(glimpse('Foo bar\n-------'), 'Foo bar')

    def test_to_html(self):
        text = '''# Title

`pdoc.Module` is a `Doc`, not `dict`.

ref with underscore: `_x_x_`

```
code block
```
reference: `package.foo`
'''
        expected = '''<h1 id="title">Title</h1>
<p><code><a href="#pdoc.Module">Module</a></code> is a <code><a href="#pdoc.Doc">Doc</a></code>,\
 not <code>dict</code>.</p>
<p>ref with underscore: <code><a href="#pdoc._x_x_">_x_x_</a></code></p>
<pre><code>code block
</code></pre>
<p>reference: <code><a href="/package.foo.ext">package.foo</a></code></p>'''

        module = PDOC_PDOC_MODULE
        module.doc['_x_x_'] = pdoc.Variable('_x_x_', module, '')

        def link(dobj):
            return '<a href="{}">{}</a>'.format(dobj.url(relative_to=module), dobj.qualname)

        html = to_html(text, module=module, link=link)
        self.assertEqual(html, expected)

        self.assertEqual(to_html('`pdoc.Doc.url()`', module=module, link=link),
                         '<p><code><a href="#pdoc.Doc.url">Doc.url</a></code></p>')

        self.assertEqual(to_html('`foo.f()`', module=module, link=link),
                         '<p><code><a href="/foo.f().ext">foo.f()</a></code></p>')

    def test_to_html_refname(self):
        text = '''
[`pdoc` x][pdoc] `pdoc`
[x `pdoc`][pdoc] `[pdoc]()`

`__x__`

[`pdoc`](#)
[``pdoc` ``](#)
[```pdoc```](#)

```
pdoc
```

[pdoc]: #pdoc
'''
        expected = '''\
<p><a href="#pdoc"><code>pdoc</code> x</a> <code><a>pdoc</a></code>
<a href="#pdoc">x <code>pdoc</code></a> <code>[<a>pdoc</a>]()</code></p>
<p><code>__x__</code></p>
<p><a href="#"><code>pdoc</code></a>
<a href="#"><code>pdoc`</code></a>
<a href="#"><code>pdoc</code></a></p>
<pre><code>pdoc
</code></pre>\
'''

        def link(dobj):
            return '<a>{}</a>'.format(dobj.qualname)

        html = to_html(text, module=PDOC_PDOC_MODULE, link=link)
        self.assertEqual(html, expected)

    def test_to_html_refname_warning(self):
        mod = EXAMPLE_PDOC_MODULE

        def f():
            """Reference to some `example_pkg.nonexisting` object"""

        mod.doc['__f'] = pdoc.Function('__f', mod, f)
        with self.assertWarns(ReferenceWarning) as cm:
            mod.html()
        del mod.doc['__f']
        self.assertIn('example_pkg.nonexisting', cm.warning.args[0])

    def test_extract_toc(self):
        text = '''xxx

# Title

>>> # doctests skipped
# doctest output, skipped

## Subtitle

```
>>> # code skipped
# skipped
```

# Title 2

```
>>> # code skipped
# skipped
```

## Subtitle 2
'''
        expected = '''<div class="toc">
<ul>
<li><a href="#title">Title</a><ul>
<li><a href="#subtitle">Subtitle</a></li>
</ul>
</li>
<li><a href="#title-2">Title 2</a><ul>
<li><a href="#subtitle-2">Subtitle 2</a></li>
</ul>
</li>
</ul>
</div>'''
        toc = extract_toc(text)
        self.assertEqual(toc, expected)

    @unittest.skipIf(shutil.which("git") is None or not os.path.exists('.git'),
                     "git not installed or we're not within git repo")
    def test_format_git_link(self):
        url = format_git_link(
            template='https://github.com/pdoc3/pdoc/blob/{commit}/{path}#L{start_line}-L{end_line}',
            dobj=EXAMPLE_PDOC_MODULE.find_ident('module.foo'),
        )
        self.assertIsInstance(url, str)
        self.assertRegex(url, r"https://github.com/pdoc3/pdoc/blob/[0-9a-f]{40}"
                              r"/pdoc/test/example_pkg/module.py#L\d+-L\d+")


class Docformats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._module = PDOC_PDOC_MODULE
        cls._docmodule = pdoc.import_module(EXAMPLE_MODULE)

    @staticmethod
    def _link(dobj, *args, **kwargs):
        return '<a>{}</a>'.format(dobj.refname)

    def test_numpy(self):
        expected = '''<p>Summary line.</p>
<p><strong>Documentation</strong>: <a href="https://pdoc3.github.io/pdoc/doc/pdoc/">https://pdoc3.github.io/pdoc/doc/pdoc/</a>
<strong>Source Code</strong>: <a href="https://github.com/pdoc3/">https://github.com/pdoc3/</a></p>
<h2 id="parameters">Parameters</h2>
<dl>
<dt><strong><code>x1</code></strong>, <strong><code>x2</code></strong> :&ensp;<code>array_like</code></dt>
<dd>
<p>Input arrays,
description of <code>x1</code>, <code>x2</code>.</p>
<div class="admonition versionadded">
<p class="admonition-title">Added in version:&ensp;1.5.0</p>
</div>
</dd>
<dt><strong><code>x</code></strong> :&ensp;<code>{ NoneType, 'B', 'C' }</code>, optional</dt>
<dd>&nbsp;</dd>
<dt><strong><code>n</code></strong> :&ensp;<code>int</code> or <code>list</code> of <code>int</code></dt>
<dd>Description of num</dd>
<dt><strong><code>*args</code></strong>, <strong><code>**kwargs</code></strong></dt>
<dd>Passed on.</dd>
<dt><strong><code>complex</code></strong> :&ensp;<code>Union[Set[<a>pdoc.Doc</a>, <a>pdoc.Function</a>], <a>pdoc</a>]</code></dt>
<dd>The <code>List[<a>pdoc.Doc</a>]</code>s of the new signal.</dd>
</dl>
<h2 id="returns">Returns</h2>
<dl>
<dt><strong><code>output</code></strong> :&ensp;<code><a>pdoc.Doc</a></code></dt>
<dd>The output array</dd>
<dt><code>List[<a>pdoc.Doc</a>]</code></dt>
<dd>The output array</dd>
<dt><code>foo</code></dt>
<dd>&nbsp;</dd>
</dl>
<h2 id="raises">Raises</h2>
<dl>
<dt><code>TypeError</code></dt>
<dd>When something.</dd>
</dl>
<h2 id="raises_1">Raises</h2>
<dl>
<dt><code>TypeError</code></dt>
<dd>&nbsp;</dd>
</dl>
<h2 id="returns_1">Returns</h2>
<p>None.</p>
<h2 id="invalid">Invalid</h2>
<p>no match</p>
<h2 id="see-also">See Also</h2>
<p><code>fromstring</code>, <code>loadtxt</code></p>
<h2 id="see-also_1">See Also</h2>
<dl>
<dt><code><a>pdoc.text</a></code></dt>
<dd>Function a with its description.</dd>
<dt><code><a>scipy.random.norm</a></code></dt>
<dd>Random variates, PDFs, etc.</dd>
<dt><code><a>pdoc.Doc</a></code></dt>
<dd>A class description that spans several lines.</dd>
</dl>
<h2 id="examples">Examples</h2>
<pre><code class="language-python-repl">&gt;&gt;&gt; doctest
...
</code></pre>
<h2 id="notes">Notes</h2>
<p>Foo bar.</p>
<h3 id="h3-title">H3 Title</h3>
<p>Foo bar.</p>'''  # noqa: E501
        text = inspect.getdoc(self._docmodule.numpy)
        html = to_html(text, module=self._module, link=self._link)
        self.assertEqual(html, expected)

    def test_numpy_curly_brace_expansion(self):
        # See: https://github.com/mwaskom/seaborn/blob/66191d8a179f1bfa42f03749bc4a07e1c0c08156/seaborn/regression.py#L514  # noqa: 501
        text = '''Parameters
----------
prefix_{x,y}_partial : str
    some description
'''
        expected = '''<h2 id="parameters">Parameters</h2>
<dl>
<dt><strong><code>prefix_{x,y}_partial</code></strong> :&ensp;<code>str</code></dt>
<dd>some description</dd>
</dl>'''
        html = to_html(text, module=self._module, link=self._link)
        self.assertEqual(html, expected)

    def test_google(self):
        expected = '''<p>Summary line.
Nomatch:</p>
<h2 id="args">Args</h2>
<dl>
<dt><strong><code>arg1</code></strong> :&ensp;<code>str</code>, optional</dt>
<dd>Text1</dd>
<dt><strong><code>arg2</code></strong> :&ensp;<code>List[str]</code>, optional,\
 default=<code>10</code></dt>
<dd>Text2</dd>
<dt><strong><code>data</code></strong> :&ensp;<code>array-like object</code></dt>
<dd>foo</dd>
</dl>
<h2 id="args_1">Args</h2>
<dl>
<dt><strong><code>arg1</code></strong> :&ensp;<code>int</code></dt>
<dd>Description of arg1</dd>
<dt><strong><code>arg2</code></strong> :&ensp;<code>str</code> or <code>int</code></dt>
<dd>Description of arg2</dd>
<dt><strong><code>test_sequence</code></strong></dt>
<dd>
<p>2-dim numpy array of real numbers, size: N * D
- the test observation sequence.</p>
<pre><code>test_sequence =
code
</code></pre>
<p>Continue.</p>
</dd>
<dt><strong><code>*args</code></strong></dt>
<dd>passed around</dd>
</dl>
<h2 id="returns">Returns</h2>
<dl>
<dt><code>issue_10</code></dt>
<dd>description didn't work across multiple lines
if only a single item was listed. <code><a>inspect.cleandoc()</a></code>
somehow stripped the required extra indentation.</dd>
</dl>
<h2 id="returns_1">Returns</h2>
<p>A very special number
which is the answer of everything.</p>
<h2 id="returns_2">Returns</h2>
<dl>
<dt><code>Dict[int, <a>pdoc.Doc</a>]</code></dt>
<dd>Description.</dd>
</dl>
<h2 id="raises">Raises</h2>
<dl>
<dt><code>AttributeError</code></dt>
<dd>
<p>The <code>Raises</code> section is a list of all exceptions
that are relevant to the interface.</p>
<p>and a third line.</p>
</dd>
<dt><code>ValueError</code></dt>
<dd>If <code>arg2</code> is equal to <code>arg1</code>.</dd>
</dl>
<p>Test a title without a blank line before it.</p>
<h2 id="args_2">Args</h2>
<dl>
<dt><strong><code>A</code></strong></dt>
<dd>a</dd>
</dl>
<h2 id="examples">Examples</h2>
<p>Examples in doctest format.</p>
<pre><code class="language-python-repl">&gt;&gt;&gt; a = [1,2,3]
</code></pre>
<h2 id="todos">Todos</h2>
<ul>
<li>For module TODOs</li>
</ul>'''
        text = inspect.getdoc(self._docmodule.google)
        html = to_html(text, module=self._module, link=self._link)
        self.assertEqual(html, expected)

    def test_doctests(self):
        expected = '''<p>Need an intro paragrapgh.</p>
<pre><code>&gt;&gt;&gt; Then code is indented one level
line1
line2
</code></pre>
<p>Alternatively</p>
<pre><code>&gt;&gt;&gt; doctest
fenced code works
always
</code></pre>
<h2 id="examples">Examples</h2>
<pre><code class="language-python-repl">&gt;&gt;&gt; nbytes(100)
'100.0 bytes'
line2
</code></pre>
<p>some text</p>
<p>some text</p>
<pre><code class="language-python-repl">&gt;&gt;&gt; another doctest
line1
line2
</code></pre>
<h2 id="example">Example</h2>
<pre><code class="language-python-repl">&gt;&gt;&gt; f()
Traceback (most recent call last):
    ...
Exception: something went wrong
</code></pre>'''
        text = inspect.getdoc(self._docmodule.doctests)
        html = to_html(text, module=self._module, link=self._link)
        self.assertEqual(html, expected)

    def test_reST_directives(self):
        expected = '''<div class="admonition todo">
<p class="admonition-title">TODO</p>
<p>Create something.</p>
</div>
<div class="admonition admonition">
<p class="admonition-title">Example</p>
<p>Image shows something.</p>
<p><img alt="" src="https://www.debian.org/logos/openlogo-nd-100.png"></p>
<div class="admonition note">
<p class="admonition-title">Note</p>
<p>Can only nest admonitions two levels.</p>
</div>
</div>
<p><img alt="" src="https://www.debian.org/logos/openlogo-nd-100.png"></p>
<p>Now you know.</p>
<div class="admonition warning">
<p class="admonition-title">Warning</p>
<p>Some warning
lines.</p>
</div>
<ul>
<li>
<p>Describe some func in a list
  across multiple lines:</p>
<div class="admonition deprecated">
<p class="admonition-title">Deprecated since version:&ensp;3.1</p>
<p>Use <code>spam</code> instead.</p>
</div>
<div class="admonition versionadded">
<p class="admonition-title">Added in version:&ensp;2.5</p>
<p>The <em>spam</em> parameter.</p>
</div>
</li>
</ul>
<div class="admonition caution">
<p class="admonition-title">Caution</p>
<p>Don't touch this!</p>
</div>'''
        text = inspect.getdoc(self._docmodule.reST_directives)
        html = to_html(text, module=self._module, link=self._link)
        self.assertEqual(html, expected)

    def test_reST_include(self):
        expected = '''<pre><code class="language-python">    x = 2
</code></pre>
<p>1
x = 2
x = 3
x =</p>'''
        mod = pdoc.Module(pdoc.import_module(
            os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE, '_reST_include', 'test.py')))
        html = to_html(mod.docstring, module=mod)
        self.assertEqual(html, expected)

        # Ensure includes are resolved within docstrings already,
        # e.g. for `pdoc.html_helpers.extract_toc()` to work
        self.assertIn('Command-line interface',
                      self._module.docstring)

    def test_urls(self):
        text = """Beautiful Soup
<a href="https://travis-ci.org/cs01/pygdbmi"><img src="https://foo" /></a>
<https://foo.bar>
Work [like this](http://foo/) and [like that].
[like that]: ftp://bar
data:text/plain;base64,SGVsbG8sIFdvcmxkIQ%3D%3D
```
http://url.com
```
[https://google.com](https://google.com)
[https://en.wikipedia.org/wiki/Orange_(software)](https://en.wikipedia.org/wiki/Orange_(software))
[Check https://google.com here](https://google.com)
`https://google.com`

http://www.foo.bar
http://www.foo.bar?q="foo"
https://en.wikipedia.org/wiki/Orange_(software)
(https://google.com)
(http://foo and http://bar)
text ``x ` http://foo`` http://bar `http://foo`
"""

        expected = """<p>Beautiful Soup
<a href="https://travis-ci.org/cs01/pygdbmi"><img src="https://foo" /></a>
<a href="https://foo.bar">https://foo.bar</a>
Work <a href="http://foo/">like this</a> and <a href="ftp://bar">like that</a>.</p>
<p>data:text/plain;base64,SGVsbG8sIFdvcmxkIQ%3D%3D</p>
<pre><code>http://url.com
</code></pre>
<p><a href="https://google.com">https://google.com</a>
<a href="https://en.wikipedia.org/wiki/Orange_(software)">\
https://en.wikipedia.org/wiki/Orange_(software)</a>
<a href="https://google.com">Check https://google.com here</a>
<code>https://google.com</code></p>
<p><a href="http://www.foo.bar">http://www.foo.bar</a>
<a href="http://www.foo.bar?q=&quot;foo&quot;">http://www.foo.bar?q="foo"</a>
<a href="https://en.wikipedia.org/wiki/Orange_(software)">\
https://en.wikipedia.org/wiki/Orange_(software)</a>
(<a href="https://google.com">https://google.com</a>)
(<a href="http://foo">http://foo</a> and <a href="http://bar">http://bar</a>)
text <code>x ` http://foo</code> <a href="http://bar">http://bar</a> <code>http://foo</code></p>"""

        html = to_html(text)
        self.assertEqual(html, expected)

    def test_latex_math(self):
        expected = r'''<p>Inline equation: <span><span class="MathJax_Preview"> v_t *\frac{1}{2}* j_i + [a] &lt; 3 </span><script type="math/tex"> v_t *\frac{1}{2}* j_i + [a] < 3 </script></span>.</p>
<p>Block equation: <span><span class="MathJax_Preview"> v_t *\frac{1}{2}* j_i + [a] &lt; 3 </span><script type="math/tex; mode=display"> v_t *\frac{1}{2}* j_i + [a] < 3 </script></span></p>
<p>Block equation: <span><span class="MathJax_Preview"> v_t *\frac{1}{2}* j_i + [a] &lt; 3 </span><script type="math/tex; mode=display"> v_t *\frac{1}{2}* j_i + [a] < 3 </script></span></p>
<p><span><span class="MathJax_Preview"> v_t *\frac{1}{2}* j_i + [a] &lt; 3 </span><script type="math/tex; mode=display"> v_t *\frac{1}{2}* j_i + [a] < 3 </script></span></p>'''  # noqa: E501
        text = inspect.getdoc(self._docmodule.latex_math)
        html = to_html(text, module=self._module, link=self._link, latex_math=True)
        self.assertEqual(html, expected)

    def test_fenced_code(self):
        # GH-207
        text = '''\
```
cmd `pwd`
```
'''
        expected = '''<pre><code>cmd `pwd`\n</code></pre>'''
        html = to_html(text, module=self._module)
        self.assertEqual(html, expected)


@unittest.skipIf('win' in sys.platform, "signal.SIGALRM doesn't work on Windos")
class HttpTest(unittest.TestCase):
    """
    Unit tests for the HTTP server functionality.
    """
    @contextmanager
    def _timeout(self, secs):
        def _raise(*_):
            raise TimeoutError

        signal.signal(signal.SIGALRM, _raise)
        signal.alarm(secs)
        yield
        signal.alarm(0)

    @contextmanager
    def _http(self, modules: list):
        port = randint(9000, 12000)

        with self._timeout(1000):
            with redirect_streams() as (stdout, stderr):
                t = threading.Thread(
                    target=cli.main,
                    args=(cli.parser.parse_args(['--http', ':%d' % port] + modules),))
                t.start()
                sleep(.1)

                if not t.is_alive():
                    sys.__stderr__.write(stderr.getvalue())
                    raise AssertionError

                try:
                    yield 'http://localhost:{}/'.format(port)
                except Exception:
                    sys.__stderr__.write(stderr.getvalue())
                    sys.__stdout__.write(stdout.getvalue())
                    raise
                finally:
                    pdoc.cli._httpd.shutdown()  # type: ignore
                    t.join()

    def test_http(self):
        with self._http(['pdoc', os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE)]) as url:
            with self.subTest(url='/'):
                with urlopen(url, timeout=3) as resp:
                    html = resp.read()
                    self.assertIn(b'Python package <code>pdoc</code>', html)
                    self.assertNotIn(b'gzip', html)
            with self.subTest(url='/' + EXAMPLE_MODULE):
                with urlopen(url + 'pdoc', timeout=3) as resp:
                    html = resp.read()
                    self.assertIn(b'__pdoc__', html)
            with self.subTest(url='/csv.ext'):
                with urlopen(url + 'csv.ext', timeout=3) as resp:
                    html = resp.read()
                    self.assertIn(b'DictReader', html)

    def test_file(self):
        with chdir(os.path.join(TESTS_BASEDIR, EXAMPLE_MODULE)):
            with self._http(['_relative_import']) as url:
                with urlopen(url, timeout=3) as resp:
                    html = resp.read()
                    self.assertIn(b'<a href="/_relative_import">', html)

    def test_head(self):
        with self._http(['pdoc']) as url:
            with urlopen(Request(url + 'pdoc/',
                                 method='HEAD',
                                 headers={'If-None-Match': 'xxx'})) as resp:
                self.assertEqual(resp.status, 205)
            with self.assertRaises(HTTPError) as cm:
                urlopen(Request(url + 'pdoc/',
                                method='HEAD',
                                headers={'If-None-Match': str(os.stat(pdoc.__file__).st_mtime)}))
            self.assertEqual(cm.exception.code, 304)


if __name__ == '__main__':
    unittest.main()
