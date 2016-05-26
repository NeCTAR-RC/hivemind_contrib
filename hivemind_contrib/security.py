import os
import json
import prettytable
import six

from fabric.api import task
from fabric.utils import error

from novaclient import exceptions as n_exc

from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova
from hivemind_contrib import neutron
from hivemind_contrib import glance

from freshdesk.v2.api import API


@decorators.configurable('freshdesk')
@decorators.verbose
def get_freshdesk_config(api_key=None,
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
    return (domain, api_key)


def get_freshdesk_client():
    domain, api_key = get_freshdesk_config()
    return API(domain, api_key)


def _get_remote(rule):
    if rule['remote_ip_prefix']:
        remote = '%s (CIDR)' % rule['remote_ip_prefix']
    elif rule['remote_group_id']:
        remote = '%s (group)' % rule['remote_group_id']
    else:
        remote = None
    return remote


def _get_protocol_port(rule):
    proto = rule['protocol']
    port_min = rule['port_range_min']
    port_max = rule['port_range_max']
    if proto in ('tcp', 'udp'):
        if (port_min and port_min == port_max):
            protocol_port = '%s/%s' % (port_min, proto)
        elif port_min:
            protocol_port = '%s-%s/%s' % (port_min, port_max, proto)
        else:
            protocol_port = proto
    elif proto == 'icmp':
        icmp_opts = []
        if port_min is not None:
            icmp_opts.append('type:%s' % port_min)
        if port_max is not None:
            icmp_opts.append('code:%s' % port_max)

        if icmp_opts:
            protocol_port = 'icmp (%s)' % ', '.join(icmp_opts)
        else:
            protocol_port = 'icmp'
    elif proto is not None:
        # port_range_min/max are not recognized for protocol
        # other than TCP, UDP and ICMP.
        protocol_port = proto
    else:
        protocol_port = None
    return protocol_port


def _format_sg_rule(rule):
    formatted = []
    for field in ['direction',
                  'ethertype',
                  ('protocol_port', _get_protocol_port),
                  'remote_ip_prefix',
                  'remote_group_id']:
        if isinstance(field, tuple):
            field, get_method = field
            data = get_method(rule)
        else:
            data = rule[field]
        if not data:
            continue
        if field in ('remote_ip_prefix', 'remote_group_id'):
            data = '%s: %s' % (field, data)
        formatted.append(data)
    return ', '.join(formatted)


def _format_sg_rules(secgroup):
    try:
        return '\n'.join(sorted([_format_sg_rule(rule) for rule
                                 in secgroup['security_group_rules']]))
    except Exception:
        return ''


def _format_secgroups(security_groups, style=None):
    pt = prettytable.PrettyTable(['ID', 'Name', 'Rules'], caching=False)
    pt.align = 'l'
    for sg in security_groups['security_groups']:
        pt.add_row([sg['id'], sg['name'],
                    _format_sg_rules(sg)])

    if style == 'html':
        output = '<b>Security Groups</b>'
        output += pt.get_html_string(attributes={
            'border': 1,
            'style': 'border-width: 1px; border-collapse: collapse;'
        })
    else:
        output = 'Security Groups:\n'
        output += pt.get_string()
    return output


def _format_instance(d, style=None):
    """Pretty print instance info for the command line"""
    pt = prettytable.PrettyTable(['Property', 'Value'], caching=False)
    pt.align = 'l'
    for k, v in sorted(d.items()):
        # convert dict to str to check length
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        # if value has a newline, add in multiple rows
        # e.g. fault with stacktrace
        if v and isinstance(v, six.string_types) and (r'\n' in v or '\r' in v):
            # '\r' would break the table, so remove it.
            if '\r' in v:
                v = v.replace('\r', '')
            lines = v.strip().split(r'\n')
            col1 = k
            for line in lines:
                pt.add_row([col1, line])
                col1 = ''
        else:
            if v is None:
                v = '-'
            pt.add_row([k, v])

    if style == 'html':
        output = '<b>Instance details</b>'
        output += pt.get_html_string(attributes={
            'border': 1,
            'style': 'border-width: 1px; border-collapse: collapse;'
        })
    else:
        output = 'Instance details:\n'
        output += pt.get_string()
    return output


def _generate_instance_info(instance_id, style=None):
    nc = nova.client()
    kc = keystone.client()
    gc = glance.get_glance_client(kc)
    qc = neutron.get_neutron_client()

    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error("Instance {} not found".format(instance_id))

    info = instance._info.copy()
    for network_label, address_list in instance.networks.items():
        info['%s network' % network_label] = ', '.join(address_list)

    flavor = info.get('flavor', {})
    flavor_id = flavor.get('id', '')

    try:
        info['flavor'] = '%s (%s)' % (nova.get_flavor(nc, flavor_id).name,
                                      flavor_id)
    except Exception:
        info['flavor'] = '%s (%s)' % ("Flavor not found", flavor_id)

    # Image
    image = info.get('image', {})
    if image:
        image_id = image.get('id', '')
        try:
            i = nova.get_image(nc, image_id)
            img = gc.images.get(image_id)
            nectar_build = 'N/A'
            if 'nectar_build' in img.properties:
                nectar_build = img.properties.get('nectar_build')
            info['image'] = ('%s\n(%s, NeCTAR Build %s)'
                             % (i.name, i.id, nectar_build))
        except Exception:
            info['image'] = '%s (%s) %s' % ('Image not found', image_id, )
    else:  # Booted from volume
        info['image'] = "Attempt to boot from volume - no image supplied"

    # Tenant
    tenant_id = info.get('tenant_id')
    if tenant_id:
        try:
            tenant = keystone.get_tenant(kc, tenant_id)
            info['tenant_id'] = '%s (%s)' % (tenant.name, tenant.id)
        except:
            pass

    # User
    user_id = info.get('user_id')
    if user_id:
        try:
            user = keystone.get_user(kc, user_id)
            info['user_id'] = '%s (%s)' % (user.name, user.id)
        except:
            pass

    # Security groups
    ports = qc.list_ports(device_id=instance.id)
    sg_ids = [sg for sgs in [p['security_groups']
              for p in ports['ports']] for sg in sgs]
    security_groups = qc.list_security_groups(id=sg_ids)

    # Remove stuff
    info.pop('links', None)
    info.pop('addresses', None)
    info.pop('hostId', None)
    info.pop('security_groups', None)

    string_instance = _format_instance(info, style=style)
    string_secgroups = _format_secgroups(security_groups, style=style)
    return '\n\n'.join([string_instance, string_secgroups])


@task
@decorators.verbose
def instance_info(instance_id):
    print(_generate_instance_info(instance_id))


def get_ticket_recipients(instance):
    """Build a list of email addresses"""
    email_addresses = []

    kc = keystone.client()
    user = keystone.get_user(kc, instance.user_id)
    if user.email:
        email_addresses.append(user.email)

    # Add tenant members to ticket recipient list
    tenant = keystone.get_tenant(kc, instance.tenant_id)
    for user in tenant.list_users():
        roles = [r.name for r in user.list_roles(tenant)]
        if 'TenantManager' in roles:
            email_addresses.append(user.email)
    return email_addresses


@task
@decorators.verbose
def lock_instance(instance_id, dry_run=True):
    """pause and lock an instance"""
    if dry_run:
        print('Running in dry-run mode')

    fd = get_freshdesk_client()
    nc = nova.client()
    kc = keystone.client()
    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error('Instance {} not found'.format(instance_id))

    ticket_id = None
    ticket_url = instance.metadata.get('security_ticket')
    if ticket_url:
        print('Found existing ticket: {}'.format(ticket_url))
        ticket_id = int(ticket_url.split('/')[-1])

        if dry_run:
            print('Would set ticket #{} status to open/urgent'
                  .format(ticket_id))
        else:
            # Set ticket status=open, priority=urgent
            print('Setting ticket #{} status to open/urgent'.format(ticket_id))
            fd.tickets.update_ticket(ticket_id, status=2, priority=4)
    else:
        tenant = keystone.get_tenant(kc, instance.tenant_id)
        user = keystone.get_user(kc, instance.user_id)
        email_addresses = get_ticket_recipients(instance)

        # Create ticket if none exist, and add instance info
        subject = 'Security incident for instance {}'.format(instance_id)
        body = '<br />\n'.join([
            'Dear NeCTAR Research Cloud User, ',
            '',
            '',
            'We have reason to believe that cloud instance: '
            '<b>{} ({})</b>'.format(instance.name, instance.id),
            'in the project <b>{}</b>'.format(tenant.name),
            'created by <b>{}</b>'.format(user.email),
            'has been involved in a security incident.',
            '',
            'We have opened this helpdesk ticket to track the details and ',
            'the progress of the resolution of this issue.',
            '',
            'Please reply to this email if you have any questions or ',
            'concerns.',
            '',
            'Thanks, ',
            'NeCTAR Research Cloud Team'
        ])

        if dry_run:
            print('Would create ticket with details:')
            print('  To:      {}'.format(','.join(email_addresses)))
            print('  Subject: {}'.format(subject))

            print('Would add instance details to ticket:')
            print(_generate_instance_info(instance_id))
        else:
            print('Creating new Freshdesk ticket')
            ticket = fd.tickets.create_ticket(
                description=body,
                subject=subject, email='no-reply@rc.nectar.org.au',
                priority=4, cc_emails=email_addresses, tags=['security'])
            ticket_id = ticket.id
            ticket_url = 'https://{}/helpdesk/tickets/{}'\
                         .format(fd.domain, ticket_id)
            nc.servers.set_meta(instance_id, {'security_ticket': ticket_url})
            print('Ticket #{} has been created: {}'
                  .format(ticket_id, ticket_url))

            # Add a private note with instance details
            print('Adding instance information to ticket')
            instance_info = _generate_instance_info(instance_id, style='html')
            fd.comments.create_note(ticket_id, instance_info)

    if dry_run:
        print('Would pause and lock instance {}'.format(instance_id))
        print('Would update ticket with action')
    else:
        # Pause and lock
        if instance.status == 'PAUSED':
            print('Instance already paused, skipping')
        else:
            print('Pausing instance {}'.format(instance_id))
            instance.pause()

        print('Locking instance {}'.format(instance_id))
        instance.lock()

        # Add reply to user
        print('Replying to ticket with action details')
        action = 'Instance <b>{} ({})</b> has been <b>paused and locked</b> '\
                 'pending further investigation'\
                 .format(instance.name, instance_id)
        fd.comments.create_reply(ticket_id, action)


@task
@decorators.verbose
def unlock_instance(instance_id, dry_run=True):
    """unlock an instance"""
    if dry_run:
        print('Running in dry-run mode')

    fd = get_freshdesk_client()
    nc = nova.client()
    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error('Instance {} not found'.format(instance_id))

    ticket_id = None
    ticket_url = instance.metadata.get('security_ticket')
    if ticket_url:
        print('Found ticket: {}'.format(ticket_url))
        ticket_id = int(ticket_url.split('/')[-1])
    else:
        if not dry_run:
            error('No ticket found in instance metadata!')

    if dry_run:
        print('Would unpause and unlock instance {}'.format(instance_id))
        print('Would reply to ticket')
        print('Would resolve ticket')
    else:
        if instance.status != 'PAUSED':
            print('Instance not paused')
        else:
            print('Unpausing instance {}'.format(instance_id))
            instance.unpause()

        print('Unlocking instance {}'.format(instance_id))
        instance.unlock()

        # Add reply to user
        print('Replying to ticket with action details')
        action = 'Instance <b>{} ({})</b> has been <b>unpaused and '\
                 'unlocked</b>'.format(instance.name, instance_id)
        fd.comments.create_reply(ticket_id, action)

        # Set ticket status=resolved
        print('Setting ticket #{} status to resolved'.format(ticket_id))
        fd.tickets.update_ticket(ticket_id, status=4)


@task
@decorators.verbose
def delete_instance(instance_id, dry_run=True):
    """delete an instance"""
    if dry_run:
        print('Running in dry-run mode')

    fd = get_freshdesk_client()
    nc = nova.client()
    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error('Instance {} not found'.format(instance_id))

    ticket_id = None
    ticket_url = instance.metadata.get('security_ticket')
    if ticket_url:
        print('Found ticket: {}'.format(ticket_url))
        ticket_id = int(ticket_url.split('/')[-1])
    else:
        if not dry_run:
            error('No ticket found in instance metadata!')

    # DELETE!!!
    if dry_run:
        print('Would delete instance {}'.format(instance_id))
        print('Would reply to ticket')
        print('Would resolve ticket')
    else:
        print('Deleting instance {})'.format(instance_id))
        instance.delete()

        # Add reply to user
        print('Updating ticket with action')
        action = 'Instance <b>{} ({})</b> has been <b>deleted.</b>'\
                 .format(instance.name, instance_id)
        fd.comments.create_reply(ticket_id, action)

        # Set ticket status=resolved
        print('Resolving ticket #{}'.format(ticket_id))
        fd.tickets.update_ticket(ticket_id, status=4)
