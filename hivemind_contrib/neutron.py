from neutronclient.neutron import client

from hivemind.decorators import configurable
from hivemind_contrib import keystone as hv_keystone


@configurable('nectar.openstack.client')
def get_neutron_client(version='2.0'):
    sess = hv_keystone.get_session()
    return client.Client(version, session=sess)
