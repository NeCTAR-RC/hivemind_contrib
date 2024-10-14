import datetime
import json

from fabric.api import task
from fabric.utils import error

from hivemind.decorators import configurable
from hivemind_contrib import keystone

import muranoclient.client as murano

import sqlalchemy as sa

# Database schema
metadata = sa.MetaData()
environment = sa.Table(
    'environment',
    metadata,
    sa.Column('created', sa.DateTime()),
    sa.Column('updated', sa.DateTime()),
    sa.Column('id', sa.String(length=255)),
    sa.Column('name', sa.String(length=255)),
    sa.Column('tenant_id', sa.String(length=36)),
    sa.Column('version', sa.BigInteger()),
    sa.Column('description', sa.Text()),
)


@configurable('connection')
def connect(uri):
    engine = sa.create_engine(uri)
    return engine.connect()


@configurable('nectar.openstack.client')
def client(version='1', project_name=None):
    sess = keystone.get_session(tenant_name=project_name)
    return murano.Client(
        version, session=sess, service_type='application-catalog'
    )


@task
def report():
    """Fetch records from DB and generate usage report"""
    db = connect()
    sql = sa.select([environment])
    env_list = db.execute(sql)

    report_date = datetime.date.today().isoformat()

    for env in env_list:
        data = json.loads(env[environment.c.description])
        pkgs = get_packages(data)
        for pkg in pkgs:
            print(
                '{},{},{},{},{},{},{}'.format(
                    report_date,
                    env[environment.c.created],
                    env[environment.c.tenant_id],
                    env[environment.c.name],
                    pkg['name'],
                    pkg['az'],
                    pkg['inst'],
                )
            )


def get_packages(data):
    """get list of packages and instance info from json data"""
    instances = []
    packages = []
    objects = data.get('Objects')
    if not objects:
        return packages
    services = objects.get('services')
    if not services:
        return packages
    # do a first pass to make a list of instances
    for service in services:
        instance = dict()
        svcClass = service.get('?')
        if not svcClass:
            continue
        instance['pkg'] = svcClass.get('id')
        svcInst = service.get('instance')
        if not svcInst:
            continue
        instance['az'] = svcInst.get('availabilityZone')
        instance['id'] = svcInst.get('openstackId')
        instances.append(instance)
    # do a second pass to get packages and instance info
    for service in services:
        package = dict()
        svcClass = service.get('?')
        if not svcClass:
            continue
        package['name'] = svcClass.get('package')
        if not package['name']:
            continue
        package['az'] = None
        package['inst'] = None
        package_id = svcClass.get('id')
        # see if package id is in the list of instances
        for i in instances:
            if i['pkg'] == package_id:
                package['az'] = i['az']
                package['inst'] = i['id']
                if package['az'] and package['inst']:
                    break
        # if not, see if any other package attributes reference
        # a package id that is in the list of instances
        if not package['az']:
            for i in instances:
                for v in service.values():
                    if i['pkg'] == v:
                        package['az'] = i['az']
                        package['inst'] = i['id']
                        if package['az'] and package['inst']:
                            break
                if package['az'] and package['inst']:
                    break
        # if still not, see if any other services attributes
        # reference this package
        if not package['az']:
            for s in services:
                for v in s.values():
                    if package_id == v:
                        i = s.get('instance')
                        if i:
                            package['az'] = i.get('availabilityZone')
                            package['inst'] = i.get('openstackId')
                            if package['az'] and package['inst']:
                                break
                if package['az'] and package['inst']:
                    break
        packages.append(package)
    return packages


def _package_set(package_id, state, dry_run):
    """Set package state"""

    if state == 'public':
        set_public = True
    elif state == 'private':
        set_public = False
    else:
        error(f'Invalid state: {state}')

    mc = client()
    package = mc.packages.get(package_id)

    if package.is_public != set_public:
        if dry_run:
            print(
                f"Would set {state} flag for package {package.name} ({package_id})"
            )
        else:
            print(
                f"Setting {state} flag for package {package.name} for {package_id}"
            )
            mc.packages.toggle_public(package_id)
    else:
        print(f"Package is already {state}")


@task
def set_private(package_id, dry_run=True):
    """Set a package to private"""
    _package_set(package_id, 'private', dry_run)


@task
def set_public(package_id, dry_run=True):
    """Set a package to public"""
    _package_set(package_id, 'public', dry_run)
