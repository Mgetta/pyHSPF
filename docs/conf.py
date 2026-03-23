import os
import sys

sys.path.insert(0, os.path.abspath('../../src'))

project = 'pyHSPF'
author = 'Mulu Fratkin'
release = '2.1.3'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
]

napoleon_numpy_docstring = True

autodoc_mock_imports = [
    'pandas',
    'numpy',
    'numba',
    'networkx',
    'tables',
    'requests',
]

html_theme = 'alabaster'

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
}
