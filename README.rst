# Hivemind Contrib

A repository containing a collection of hivemind tasks.

## Installation

This repository should be installed following the documentation at:

https://github.com/NeCTAR-RC/hivemind

## Dependencies

### ospurge

For the ospurge command, you will require the NeCTAR fork of ospurge to be
installed and available in your path.

You can install directory from GitHub with pip:

```sh
pip install git+https://github.com/NeCTAR-RC/ospurge.git
```

This will only purge the following resources:
 * Cinder Snapshots
 * Cinder Backups
 * Nova Servers
 * Neutron Interfaces
 * Neutron Ports
 * Neutron Networks
 * Neutron Secgroups
 * Glance Images (that are not public or shared)
 * Swift Objects
 * Swift Containers
 * Cinder Volumes
 * Ceilometer Alarms
 * Heat Stacks


### git-buildpackage

The pbuilder packaging commands require the Ubuntu `git-buildpackage` package
to be installed. You should modify your sudoers configuration so that
cowbuilder can be run as root without entering a password. So create a file
/etc/sudoers.d/cowbuilder with content like the following::

    andrew ALL=NOPASSWD:SETENV:/usr/sbin/cowbuilder

