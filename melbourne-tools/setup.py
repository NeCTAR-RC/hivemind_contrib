#!/usr/bin/env python

from setuptools import find_packages
from setuptools import setup

setup(
    name='melbourne-tools',
    version='0.4.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'python-cinderclient>=4.2.0',
        'python-dateutil>=2.8.0',
        'python-designateclient>=2.11.0',
        'python-glanceclient>=2.16.0',
        'python-keystoneclient>=3.19.0',
        'python-neutronclient>=6.12.0',
        'python-novaclient>=14.1.0',
        'python-openstackclient>=3.18.0',
        'python-swiftclient>=3.7.0',
        'nectarallocationclient>=0.7.0',
        'click>=7.0',
        'prettytable>=0.7.0',
        'ipaddress>=1.0.0',
        'configparser>=3.7.4',
        'requests>=2.21.0',
        'ssh2-python>=0.17.0',
        'humanize>=0.5.0',
        'tenacity>=5.0.0',
    ],
    entry_points={
        'console_scripts': [
            'mydesignate=scripts.designate:cli',
            'mynova=scripts.nova:cli',
            'tempest=scripts.tempest:cli',
        ]
    },
)
