import os

from fabric.api import task
from keystoneclient.v2_0 import client as keystone_client
from keystoneclient.exceptions import NotFound

from hivemind.decorators import verbose, configurable


@configurable('nectar.openstack.client')
def client(url=None, username=None, password=None, tenant=None):
    url = os.environ.get('OS_AUTH_URL', url)
    username = os.environ.get('OS_USERNAME', username)
    password = os.environ.get('OS_PASSWORD', password)
    tenant = os.environ.get('OS_TENANT_NAME', tenant)
    assert url and username and password and tenant
    return keystone_client.Client(username=username,
                                  password=password,
                                  tenant_name=tenant,
                                  insecure=True,
                                  auth_url=url)


def get_tenant(keystone, name_or_id):
    try:
        tenant = keystone.tenants.get(name_or_id)
    except NotFound:
        tenant = keystone.tenants.find(name=name_or_id)
    return tenant


@task
@verbose
def set_vicnode_id(tenant, vicnode_id):
    """Used in RDSI reporting to determine if the allocation should appear
    in the report.

    """
    keystone = client()
    tenant = get_tenant(keystone, tenant)
    keystone.tenants.update(tenant.id, vicnode_id=vicnode_id)
