from setuptools import setup, find_packages


readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

requirements = [
    'python-designateclient',
    'python-glanceclient',
    'python-keystoneclient',
    'python-novaclient',
    'python-swiftclient',
    'python-neutronclient',
    'python-muranoclient',
    'prettytable==0.7.2',
    'keystoneauth1==5.0.0',
    'hivemind',
    'sqlalchemy',
    'pymysql',
    'requests',
    'jinja2',
    'pygithub'
]

setup(
    name='hivemind-contrib',
    version='0.1.0',
    description='A collection of plugins for use with Hivemind.',
    long_description=readme + '\n\n' + history,
    author='Russell Sim',
    author_email='russell.sim@gmail.com',
    url='https://github.com/NeCTAR-RC/hivemind_contrib',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
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
    entry_points="""
      # -*- Entry points: -*-

      [hivemind.modules]
      code = hivemind_contrib.code
      designate = hivemind_contrib.designate
      gerrit = hivemind_contrib.gerrit
      gitea = hivemind_contrib.gitea
      glance = hivemind_contrib.glance
      iptables = hivemind_contrib.iptables
      keystone = hivemind_contrib.keystone
      libvirt = hivemind_contrib.libvirt
      melbourne = hivemind_contrib.melbourne
      murano = hivemind_contrib.murano
      notification = hivemind_contrib.notification
      nova = hivemind_contrib.nova
      ospurge = hivemind_contrib.ospurge
      packages = hivemind_contrib.packages
      packaging = hivemind_contrib.debpackaging
      pbuilder = hivemind_contrib.pbuilder
      placement = hivemind_contrib.placement
      puppetdb = hivemind_contrib.puppetdb.tasks
      rcshibboleth = hivemind_contrib.rcshibboleth
      repo = hivemind_contrib.repo
      reporting = hivemind_contrib.reporting
      reports = hivemind_contrib.reports
      security = hivemind_contrib.security
      show = hivemind_contrib.show
      swift = hivemind_contrib.swift
      upgrade = hivemind_contrib.upgrade
      """,
)
