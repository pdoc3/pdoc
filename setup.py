import os
import sys
from setuptools import setup, find_packages

if sys.version_info < (3, 5):
    sys.exit('ERROR: pdoc requires Python 3.5+')


def _discover_tests():
    import unittest
    return unittest.defaultTestLoader.discover('pdoc.test')


if __name__ == '__main__':
    setup(
        name="pdoc3",
        license="AGPL-3.0",
        description="Auto-generate API documentation for Python projects.",
        long_description=open(os.path.join(os.path.dirname(__file__), 'README.md')).read(),
        long_description_content_type='text/markdown',
        url="https://pdoc3.github.io/pdoc/",
        project_urls={
            'Documentation': 'https://pdoc3.github.io/pdoc/doc/pdoc/',
            'Source': 'https://github.com/pdoc3/pdoc/',
            'Tracker': 'https://github.com/pdoc3/pdoc/issues',
        },
        classifiers=[
            "Topic :: Documentation",
            "Topic :: Software Development :: Documentation",
            "Topic :: Utilities",
            "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
            "Development Status :: 5 - Production/Stable",
            "Environment :: Console",
            "Intended Audience :: Developers",
            "Operating System :: OS Independent",
            'Programming Language :: Python :: 3 :: Only',
        ],
        entry_points={
            "console_scripts": [
                "pdoc = pdoc.cli:main",
                "pdoc3 = pdoc.cli:main",
            ],
        },
        packages=find_packages(),
        include_package_data=True,
        provides=["pdoc"],
        obsoletes=["pdoc"],
        install_requires=[
            "mako",
            "markdown >= 3.0",
        ],
        setup_requires=[
            'setuptools_git',
            'setuptools_scm',
        ],
        use_scm_version={
            'write_to': os.path.join('pdoc', '_version.py'),
        },
        test_suite="setup._discover_tests",
        python_requires='>= 3.5',
    )
