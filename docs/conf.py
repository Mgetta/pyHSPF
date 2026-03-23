# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# Add the src/ directory so Sphinx can import the hspf package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# -- Project information -----------------------------------------------------
project = 'pyHSPF'
copyright = '2024, Mulu Fratkin'
author = 'Mulu Fratkin'
release = '2.1.3'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Napoleon settings (NumPy-style docstrings) ------------------------------
napoleon_numpy_docstring = True
napoleon_google_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_rtype = True

# -- Autodoc settings --------------------------------------------------------
# Mock heavy dependencies so the docs build without the full stack installed.
autodoc_mock_imports = [
    'pandas',
    'numpy',
    'numba',
    'networkx',
    'tables',
    'requests',
]

autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}

# -- Intersphinx mapping -----------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# -- HTML output options -----------------------------------------------------
html_theme = 'alabaster'
html_static_path = ['_static']
