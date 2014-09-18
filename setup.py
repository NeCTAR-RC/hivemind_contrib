#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

requirements = [
    'python-keystoneclient',
    'python-novaclient',
    'MySQL-python',
    'prettytable',
]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='hivemind_contrib',
    version='0.1',
    description='A collection of plugins for use with Hivemind.',
    long_description=readme + '\n\n' + history,
    author='Russell Sim',
    author_email='russell.sim@gmail.com',
    url='https://github.com/russell/hivemind_contrib',
    packages=[
        'hivemind_contrib',
    ],
    package_dir={'hivemind_contrib':
                 'hivemind_contrib'},
    include_package_data=True,
    install_requires=requirements,
    license="GPLv2",
    zip_safe=False,
    keywords='hivemind_contrib',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
    ],
    test_suite='tests',
    tests_require=test_requirements,
      entry_points="""
      # -*- Entry points: -*-

      [hivemind.modules]
      gerrit = hivemind_contrib.gerrit
      iptables = hivemind_contrib.iptables
      keystone = hivemind_contrib.keystone
      libvirt = hivemind_contrib.libvirt
      nova = hivemind_contrib.nova
      packages = hivemind_contrib.packages
      packaging = hivemind_contrib.packaging
      pbuilder = hivemind_contrib.pbuilder
      puppetdb = hivemind_contrib.puppetdb.tasks
      rcshibboleth = hivemind_contrib.rcshibboleth
      repo = hivemind_contrib.repo
      swift = hivemind_contrib.swift
      upgrade = hivemind_contrib.upgrade
      """,
)
