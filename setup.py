#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup

ver_dic = {}
version_file = open("sumpy/version.py")
try:
    version_file_contents = version_file.read()
finally:
    version_file.close()

os.environ["AKPYTHON_EXEC_FROM_WITHIN_WITHIN_SETUP_PY"] = "1"
exec(compile(version_file_contents, "sumpy/version.py", "exec"), ver_dic)


# {{{ capture git revision at install time

# authoritative version in pytools/__init__.py
def find_git_revision(tree_root):
    # Keep this routine self-contained so that it can be copy-pasted into
    # setup.py.

    from os.path import join, exists, abspath
    tree_root = abspath(tree_root)

    if not exists(join(tree_root, ".git")):
        return None

    from subprocess import Popen, PIPE, STDOUT
    p = Popen(["git", "rev-parse", "HEAD"], shell=False,
              stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True,
              cwd=tree_root)
    (git_rev, _) = p.communicate()

    import sys
    if sys.version_info >= (3,):
        git_rev = git_rev.decode()

    git_rev = git_rev.rstrip()

    retcode = p.returncode
    assert retcode is not None
    if retcode != 0:
        from warnings import warn
        warn("unable to find git revision")
        return None

    return git_rev


def write_git_revision(package_name):
    from os.path import dirname, join
    dn = dirname(__file__)
    git_rev = find_git_revision(dn)

    with open(join(dn, package_name, "_git_rev.py"), "w") as outf:
        outf.write('GIT_REVISION = "%s"\n' % git_rev)


write_git_revision("sumpy")

# }}}


setup(name="sumpy",
      version=ver_dic["VERSION_TEXT"],
      description="Fast summation in Python",
      long_description="""
      Code-generating FMM etc.
      """,
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Intended Audience :: Developers",
          "Intended Audience :: Other Audience",
          "Intended Audience :: Science/Research",
          "License :: OSI Approved :: MIT License",
          "Natural Language :: English",
          "Programming Language :: Python",
          "Topic :: Scientific/Engineering",
          "Topic :: Scientific/Engineering :: Information Analysis",
          "Topic :: Scientific/Engineering :: Mathematics",
          "Topic :: Scientific/Engineering :: Visualization",
          "Topic :: Software Development :: Libraries",
          "Topic :: Utilities",
          ],

      author="Andreas Kloeckner",
      author_email="inform@tiker.net",
      license="MIT",
      packages=["sumpy", "sumpy.expansion"],

      python_requires="~=3.6",
      install_requires=[
          "pytools>=2018.2",
          "loo.py>=2017.2",
          "boxtree>=2018.1",
          "pytest>=2.3",
          "six",
          "pyrsistent>=0.16.0",

          # If this causes issues, see:
          # https://code.google.com/p/sympy/issues/detail?id=3874
          "sympy>=0.7.2",
          ])
