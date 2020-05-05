import json
import six

from fabric.api import task
from fabric.utils import error

from novaclient import exceptions as n_exc

from prettytable import PrettyTable

from hivemind import decorators
from hivemind_contrib import glance
from hivemind_contrib import keystone
from hivemind_contrib import neutron
from hivemind_contrib import nova
from hivemind_contrib.removed import moved_to_osc


def _get_sg_remote(rule):
    if rule['remote_ip_prefix']:
        remote = '%s (CIDR)' % rule['remote_ip_prefix']
    elif rule['remote_group_id']:
        remote = '%s (group)' % rule['remote_group_id']
    else:
        remote = None
    return remote


def _get_sg_protocol_port(rule):
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
                  ('protocol_port', _get_sg_protocol_port),
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
    pt = PrettyTable(['ID', 'Name', 'Rules'], caching=False)
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


def generate_instance_sg_rules_info(instance_id, style=None):
    nc = neutron.get_neutron_client()

    # Security groups
    ports = nc.list_ports(device_id=instance_id)
    sg_ids = [sg for sgs in [p['security_groups']
              for p in ports['ports']] for sg in sgs]
    security_groups = nc.list_security_groups(id=sg_ids)

    return _format_secgroups(security_groups, style=style)


def _format_instance(d, style=None):
    """Pretty print instance info for the command line"""
    pt = PrettyTable(['Property', 'Value'], caching=False)
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


def generate_instance_info(instance_id, style=None):
    nc = nova.client()
    kc = keystone.client()
    gc = glance.client()

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
            img = gc.images.get(image_id)
            nectar_build = img.get('nectar_build', 'N/A')
            info['image'] = ('%s (%s, NeCTAR Build %s)'
                             % (img.name, img.id, nectar_build))
        except Exception:
            info['image'] = 'Image not found (%s)' % image_id

    else:  # Booted from volume
        info['image'] = "Attempt to boot from volume - no image supplied"

    # Tenant
    project_id = info.get('tenant_id')
    if project_id:
        try:
            project = keystone.get_project(kc, project_id)
            info['project_id'] = '%s (%s)' % (project.name, project.id)
        except Exception:
            pass

    # User
    user_id = info.get('user_id')
    if user_id:
        try:
            user = keystone.get_user(kc, user_id)
            info['user_id'] = '%s (%s)' % (user.name, user.id)
        except Exception:
            pass

    # Remove stuff
    info.pop('links', None)
    info.pop('addresses', None)
    info.pop('hostId', None)
    info.pop('security_groups', None)

    return _format_instance(info, style=style)


@task
@decorators.verbose
def instance(instance_id):
    moved_to_osc()


@task
@decorators.verbose
def instance_sg_rules(instance_id):
    moved_to_osc()
