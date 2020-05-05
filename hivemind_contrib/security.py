from fabric.api import task
from fabric.utils import error

from novaclient import exceptions as n_exc

from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova
from hivemind_contrib.show import generate_instance_info
from hivemind_contrib.show import generate_instance_sg_rules_info

try:
    from freshdesk.v2.api import API
except ImportError:
    API = None


@decorators.configurable('freshdesk')
@decorators.verbose
def get_freshdesk_config(api_key=None,
                         email_config_id='6000071619',
                         group_id='6000208874',
                         domain='dhdnectar.freshdesk.com'):
    """fetch freshdesk API details from config file"""
    msg = '\n'.join([
        'No Freshdesk API key found in your Hivemind config file.',
        '',
        'To find your Freshdesk API key by following the guide here:',
        'https://support.freshdesk.com/support/solutions/'
        'articles/215517-how-to-find-your-api-key',
        '',
        'Then add the following config to your Hivemind configuration',
        'file (~/.hivemind/hivemind/config.ini):',
        '',
        '  [cfg:hivemind_contrib.security.freshdesk]',
        '  api_key = <your api key>',
    ])

    if api_key is None:
        error(msg)

    config = {'api_key': api_key,
              'email_config_id': email_config_id,
              'group_id': group_id,
              'domain': domain}

    return config


def get_freshdesk_client(domain, api_key):
    if not API:
        error("To use this tool, you will need to also install the"
              "python-freshdesk package: \n"
              "  $ pip install python-freshdesk")
    return API(domain, api_key)


def get_tenant_managers_emails(kc, instance):
    """Build a list of email addresses"""
    email_addresses = []
    project = keystone.get_project(kc, instance.tenant_id)
    role = kc.roles.find(name='TenantManager')
    ras = kc.role_assignments.list(project=project, role=role,
                                   include_names=True)
    for ra in ras:
        u = keystone.get_user(kc, ra.user['id'])
        email_addresses.append(u.email)
    return email_addresses


@task
@decorators.verbose
def lock_instance(instance_id, cc=None, dry_run=True):
    """pause and lock an instance

    :param str cc: An extra email address to add to the CC list
    """
    print('this function has been moved to nectar-osc client')


@task
@decorators.verbose
def unlock_instance(instance_id, dry_run=True):
    """unlock an instance"""
    print('this function has been moved to nectar-osc client')


@task
@decorators.verbose
def delete_instance(instance_id, dry_run=True):
    """delete an instance"""
    print('this function has been moved to nectar-osc client')
