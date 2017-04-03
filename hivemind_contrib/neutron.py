import os

from hivemind_contrib import keystone
from hivemind.decorators import configurable
from neutronclient.neutron import client


@configurable('nectar.openstack.client')
def get_neutron_client(version='2.0', url=None, username=None,
                       password=None, tenant=None, region=None):
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant)
    region = os.environ.get('OS_REGION_NAME', region)
    assert url and username and password and tenant

    sess = keystone.get_session(url=url, username=username, password=password,
                                tenant=tenant)

    return client.Client(version, session=sess, region_name=region)
