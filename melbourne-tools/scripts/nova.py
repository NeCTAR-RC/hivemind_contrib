#!/usr/bin/env python
#
# Nova is a generic framework for finding instances
# using python-novaclient

import click
from collections import Counter
from collections import defaultdict
from glanceclient import client as glance_client
import humanize
import itertools
from keystoneclient.v3 import client as keystone_client
from nectarallocationclient import client as allocation_client
from neutronclient.v2_0 import client as neutron_client
from novaclient import client as nova_client
from prettytable import PrettyTable
import socket
from ssh2.session import Session
from utils import get_session
from utils import parse_nodes
from utils import try_assign
# from datetime import datetime, timedelta
# from IPython import embed

# global INSTAN
# global nova
# global glance
# global keystone
# global neutron
# global allocation


def dict_product(dicts):
    """Generate a Cartesian product of dictionary of lists.

    >>> list(dict_product(dict(number=[1,2], character='ab')))
    [{'character': 'a', 'number': 1},
     {'character': 'a', 'number': 2},
     {'character': 'b', 'number': 1},
     {'character': 'b', 'number': 2}]
    """
    return (dict(zip(dicts, x)) for x in itertools.product(*dicts.values()))


def _find_hosts_in_aggregates(nova, aggregates, hosts):
    """Find hosts in aggregates."""
    if not hosts:
        return set(host for aggregate in nova.aggregates.list()
                   for host in aggregate.hosts
                   if aggregate.name in aggregates)
    else:
        return set(host for aggregate in nova.aggregates.list()
                   for host in aggregate.hosts
                   if aggregate.name in aggregates
                   if host in hosts)


def _find_hosts_in_azs(nova, zones, hosts):
    """Find hosts in the following zones."""
    if not hosts:
        return set(host for aggregate in nova.aggregates.list()
                   for host in aggregate.hosts
                   if u"availability_zone" in aggregate.metadata and
                   aggregate.metadata[u"availability_zone"] in zones)
    else:
        return set(host for aggregate in nova.aggregates.list()
                   for host in aggregate.hosts
                   if u"availability_zone" in aggregate.metadata and
                   aggregate.metadata[u"availability_zone"] in zones
                   and host in hosts)


def _find_projects(allocation, allocation_home):
    """Find project IDs with given parameters."""
    # Approved allocations
    opts = {'parent_request__isnull': True,
            'allocation_home': allocation_home}
    allocations = allocation.allocations.list(**opts)

    return set(a.project_id
               for a in allocations)


def _find_instances(nova, hosts, statuses, project_ids):
    """Find instances from nova client from the zone and statuses."""
    opts = {'all_tenants': [True]}
    if project_ids:
        opts['project_id'] = project_ids
    if statuses:
        opts['status'] = statuses
    if hosts:
        opts['host'] = hosts
    # Generate a cartesian product of the search parameters
    queries = dict_product(opts)
    for query in queries:
        for server in nova.servers.list(search_opts=query):
            yield server


def _list_instances(nova, glance, keystone, allocation, aggregate,
                    availability_zone, host, status, projects,
                    allocation_home, exclude_availability_zones,
                    exclude_host, exclude_aggregates):
    """List all instances."""
    hosts = None if host is None else parse_nodes(host)

    if aggregate:
        hosts = _find_hosts_in_aggregates(nova, aggregate, hosts)

    if availability_zone:
        hosts = _find_hosts_in_azs(nova, availability_zone, hosts)

    if not projects and allocation_home:
            projects = _find_projects(allocation, allocation_home)

    exclude_hosts = [] if exclude_host is None else parse_nodes(exclude_host)

    if exclude_aggregates:
        exclude_hosts = _find_hosts_in_aggregates(nova, exclude_aggregates,
                                                  exclude_hosts)
    if exclude_availability_zones:
        exclude_hosts = _find_hosts_in_azs(nova,
                                           exclude_availability_zones,
                                           exclude_hosts)

    output = []

    # Caching image and flavor
    USER_CACHE = {}
    PROJECT_CACHE = {}
    IMAGE_CACHE = {}
    FLAVOR_CACHE = {}
    # Augment the instance info with flavor and image
    for i in _find_instances(nova, hosts, status, projects):
        if i._info['OS-EXT-SRV-ATTR:host'] in exclude_hosts:
            continue
        flavor_id = i.flavor['id']
        if flavor_id not in FLAVOR_CACHE:
            FLAVOR_CACHE[flavor_id] = nova.flavors.get(flavor_id)._info
        i._info['flavor'] = FLAVOR_CACHE[flavor_id]
        if i.image:
            if i.image['id'] not in IMAGE_CACHE:
                image = try_assign(glance.images.get, i.image['id'])
                if not image:
                    image = {'name': '',
                             'vcpus': '',
                             'ram': '',
                             'swap': '',
                             'disk': '',
                             'rxtx_factor': ''}
                IMAGE_CACHE[i.image['id']] = image
            i._info['image'] = IMAGE_CACHE[i.image['id']]
        else:
            i._info['image'] = {'name': '',
                                'vcpus': '',
                                'ram': '',
                                'swap': '',
                                'disk': '',
                                'rxtx_factor': ''}
        i._info['project_id'] = i._info['tenant_id']
        if i._info['project_id'] not in PROJECT_CACHE:
            PROJECT_CACHE[i._info['project_id']] = keystone.projects.get(
                                                   i._info['project_id'])
        i._info['project'] = PROJECT_CACHE[i._info['project_id']]
        if i._info['user_id'] not in USER_CACHE:
            USER_CACHE[i._info['user_id']] = keystone.users.get(
                                             i._info['user_id'])
        i._info['user'] = USER_CACHE[i._info['user_id']]
        output.append(i)
    return output


def _render_table_instances(instances, columns, sortby):
    """Render instances in table format."""
    table = PrettyTable()
    fields = [col for col in columns]
    if not columns:
        fields = ['id', 'name', 'status', 'flavor',
                  'OS-EXT-SRV-ATTR:host', 'addresses']
    table.field_names = fields
    table.align = 'l'
    for ins in instances:
        row = []
        for f in fields:
            if 'flavor' in f:
                if f in 'flavor':
                    row.append(ins._info['flavor']['name'])
                else:
                    attr = f.split(':')[1]
                    row.append(ins._info['flavor'][attr])
            elif f in 'project' or f in 'tenant':
                row.append(ins._info['project'].name)
            elif f in 'user':
                row.append(ins._info['user'].email)
            elif f in 'security_groups':
                row.append(', '.join(sc['name']
                                     for sc in ins._info['security_groups']))
            elif f in 'image':
                row.append(ins._info['image']['name'])
            elif f in 'addresses':
                output = ["%s=%s" % (k, ','.join(v))
                          for k, v in ins.networks.items()]
                row.append(';'.join(output))
            else:
                row.append(ins._info[f])
        table.add_row(row)
    if sortby:
        table.sortby = sortby
    click.echo(table)


def _render_table_instance(instance):
    """Render the instance in table format."""
    table = PrettyTable(['Property', 'Value'])
    table.align = 'l'
    fields = ['OS-EXT-AZ:availability_zone', 'OS-EXT-SRV-ATTR:host',
              'OS-EXT-SRV-ATTR:instance_name', 'OS-EXT-STS:task_state',
              'OS-EXT-STS:vm_state', 'created', 'flavor:name',
              'flavor:ram', 'flavor:vcpus', 'id', 'image',
              'key_name', 'metadata', 'name',
              'os-extended-volumes:volumes_attached', 'status']
    fields.extend("%s network" % az
                  for az in instance._info['addresses'].keys())
    fields.extend(['updated', 'user_id'])
    for f in fields:
        table.add_row([f, instance._info[f]])
    click.echo(table)


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


def _format_secgroups(security_groups):
    pt = PrettyTable(['ID', 'Name', 'Rules'], caching=False)
    pt.align = 'l'
    for sg in security_groups['security_groups']:
        pt.add_row([sg['id'], sg['name'],
                    _format_sg_rules(sg)])

    output = 'Security Groups:\n'
    output += pt.get_string()
    return output


def generate_instance_sg_rules_info(neutron, instance_id):
    """Generate instance security groups."""
    # Security groups
    ports = neutron.list_ports(device_id=instance_id)
    sg_ids = [sg for sgs in (p['security_groups']
              for p in ports['ports']) for sg in sgs]
    security_groups = neutron.list_security_groups(id=sg_ids)

    return security_groups


def _recommend_nmap_command(ports, ip):
    """Display recommendation for using nmap."""
    click.echo("Globally opened ports found: %s" % ports)
    command = "nmap -sV -sT -sC -p %s %s" % (','.join(ports),
                                             ip)
    return command


@click.group()
def cli():
    """Extend nova search functionality."""
    pass


@cli.group()
def security():
    """Security related functionality."""
    pass


@cli.group()
def aggregate():
    """Aggregate related functionality."""
    pass


@cli.command()
@click.option('--host',
              help='Only list instances from HOST (eg. qh2-rcc[10-99])')
@click.option('--exclude-host',
              help='Exclude instances from HOST(eg. qh2-rcc[10-99])')
@click.option('-s', '--status', multiple=True,
              help='Only list instances with STATUS')
@click.option('-az', '--availability-zone', multiple=True,
              help='Only list instances in AVAILABILITY ZONE')
@click.option('--exclude-availability-zone', multiple=True,
              help='Exclude instances in AVAILABILITY_ZONE')
@click.option('-ag', '--aggregate', multiple=True,
              help='Only list instances in AGGREGATE')
@click.option('--exclude-aggregate', multiple=True,
              help='Exclude instances in AGGREGATE')
@click.option('-lc', '--last-changed',
              help='Only list instances that changed since LAST-CHANGED')
@click.option('--project', multiple=True,
              help='Only list instances from PROJECT_ID')
@click.option('-c', '--column', multiple=True,
              help='Include the following columns when rendering table format',
              type=click.Choice(['OS-EXT-STS:task_state', 'addresses', 'links',
                                 'image', 'OS-EXT-STS:vm_state',
                                 'OS-EXT-SRV-ATTR:instance_name',
                                 'OS-SRV-USG:launched_at', 'flavor', 'id',
                                 'security_groups', 'user_id',
                                 'OS-DCF:diskConfig', 'accessIPv4',
                                 'accessIPv6', 'progress',
                                 'OS-EXT-STS:power_state',
                                 'OS-EXT-AZ:availability_zone',
                                 'config_drive', 'status', 'updated', 'hostId',
                                 'OS-EXT-SRV-ATTR:host',
                                 'OS-SRV-USG:terminated_at',
                                 'key_name',
                                 'OS-EXT-SRV-ATTR:hypervisor_hostname',
                                 'name', 'created', 'tenant_id',
                                 'os-extended-volumes:volumes_attached',
                                 'metadata', 'project_id', 'user',
                                 'project', 'tenant', 'flavor:disk',
                                 'flavor:rxtx_factor',
                                 'flavor:ram', 'flavor:swap', 'flavor:vcpus']))
@click.option('--sort-by',
              help='Sort by the selected column',
              type=click.Choice(['OS-EXT-STS:task_state', 'addresses', 'links',
                                 'image', 'OS-EXT-STS:vm_state',
                                 'OS-EXT-SRV-ATTR:instance_name',
                                 'OS-SRV-USG:launched_at', 'flavor', 'id',
                                 'security_groups', 'user_id',
                                 'OS-DCF:diskConfig', 'accessIPv4',
                                 'accessIPv6', 'progress',
                                 'OS-EXT-STS:power_state',
                                 'OS-EXT-AZ:availability_zone',
                                 'config_drive', 'status', 'updated', 'hostId',
                                 'OS-EXT-SRV-ATTR:host',
                                 'OS-SRV-USG:terminated_at',
                                 'key_name',
                                 'OS-EXT-SRV-ATTR:hypervisor_hostname',
                                 'name', 'created', 'tenant_id',
                                 'os-extended-volumes:volumes_attached',
                                 'metadata', 'project_id', 'user',
                                 'project', 'tenant', 'flavor:disk',
                                 'flavor:rxtx_factor',
                                 'flavor:ram', 'flavor:swap', 'flavor:vcpus']))
@click.option('--allocation-home',
              help='Filter by an ALLOCATION_HOME')
def list(host=None, last_changed=None, availability_zone=None, column=None,
         aggregate=None, status=None, sort_by=None, project=None,
         allocation_home=None, exclude_availability_zone=None,
         exclude_host=None, exclude_aggregate=None):
    """List all nova instances with given parameters."""
    session = get_session()
    nova = nova_client.Client(2, session=session)
    glance = glance_client.Client(2, session=session)
    keystone = keystone_client.Client(session=session)
    allocation = allocation_client.Client(1, session=session)
    instances = _list_instances(nova, glance, keystone, allocation, aggregate,
                                availability_zone, host, status, project,
                                allocation_home, exclude_availability_zone,
                                exclude_host, exclude_aggregate)
    # INSTAN = instances
    # embed()
    if not column:
        sort_by = 'OS-EXT-SRV-ATTR:host'
    _render_table_instances(instances, column, sort_by)


@cli.command()
@click.option('--host',
              help='Only list instances from HOST (eg. qh2-rcc[10-99])')
@click.option('--exclude-host',
              help='Exclude instances from HOST(eg. qh2-rcc[10-99])')
@click.option('-s', '--status', multiple=True,
              help='Only list instances with STATUS')
@click.option('-az', '--availability-zone', multiple=True,
              help='Only list instances in AVAILABILITY ZONE')
@click.option('--exclude-availability-zone', multiple=True,
              help='Exclude instances in AVAILABILITY_ZONE')
@click.option('-ag', '--aggregate', multiple=True,
              help='Only list instances in AGGREGATE')
@click.option('--exclude-aggregate', multiple=True,
              help='Exclude instances in AGGREGATE')
@click.option('-lc', '--last-changed',
              help='Only target instances that changed since LAST-CHANGED')
@click.option('--project', multiple=True,
              help='Only list instances from PROJECT_ID')
@click.option('--allocation-home',
              help='Filter by an ALLOCATION_HOME')
@click.option('--detail', is_flag=True,
              help='DETAIL the instance statistic by projects')
def stat(host=None, last_changed=None, availability_zone=None,
         aggregate=None, status=None, project=None,
         allocation_home=None, exclude_availability_zone=None,
         exclude_host=None, exclude_aggregate=None,
         detail=None):
    """Gather statistic of all nova instances with given parameters."""
    session = get_session()
    nova = nova_client.Client(2, session=session)
    glance = glance_client.Client(2, session=session)
    keystone = keystone_client.Client(session=session)
    allocation = allocation_client.Client(1, session=session)
    instances = _list_instances(nova, glance, keystone, allocation, aggregate,
                                availability_zone, host, status, project,
                                allocation_home, exclude_availability_zone,
                                exclude_host, exclude_aggregate)
    # Summary table
    table = PrettyTable(['Name', 'Value'])
    data = {'instances': 0,
            'vcpus': 0,
            'ram': 0}
    table.align = 'l'
    projects_counter = Counter()
    # Detail table
    dt = PrettyTable(['Project', 'Instances', 'vCPUs', 'RAM'])
    projects = defaultdict(lambda: defaultdict(int))
    dt.align = 'l'
    for ins in instances:
        project_name = ins._info['project'].name
        projects[project_name]['instances'] += 1
        data['instances'] += 1
        projects_counter[ins._info['project'].name] += 1
        if not ins._info['flavor']['vcpus']:
            continue
        data['vcpus'] += int(ins._info['flavor']['vcpus'])
        data['ram'] += int(ins._info['flavor']['ram'])
        projects[project_name]['vcpus'] += int(ins._info['flavor']['vcpus'])
        projects[project_name]['ram'] += int(ins._info['flavor']['ram'])

    data['common'] = ',\n'.join('%s: %d' % (k, v)
                                for k, v in projects_counter.most_common(3))
    # Convert the data to bytes for humanization
    data['ram'] = data['ram']*1024*1024
    table.add_row(['Total instances', data['instances']])
    table.add_row(['vCPUs used', data['vcpus']])
    table.add_row(['RAM used', humanize.naturalsize(data['ram'], binary=True)])
    table.add_row(['Total projects affected', len(projects_counter.keys())])
    table.add_row(['Top projects affected', data['common']])
    click.echo(table)

    if detail:
        for name, p in projects.items():
            dt.add_row([name,
                        p['instances'],
                        p['vcpus'],
                        humanize.naturalsize(p['ram']*1024*1024, binary=True)])
        click.echo(dt)


@security.command(name='investigate')
@click.argument('ip')
def security_investigate(ip):
    """Investigate the server at IP address.

    Use ssh-agent key to find the VM bridge interface and test its
    SSH authentication method.
    """
    session = get_session()
    nova = nova_client.Client(2, session=session)
    glance = glance_client.Client(2, session=session)
    neutron = neutron_client.Client(session=session)
    opts = {'all_tenants': True,
            'ip': ip}
    instances = nova.servers.list(search_opts=opts, limit=1)
    if not instances:
        return
    instance = instances[0]

    target_mac_device = None
    target_host = instance._info['OS-EXT-SRV-ATTR:hypervisor_hostname']
    target_instance_name = instance._info['OS-EXT-SRV-ATTR:instance_name']
    # Augment the retrieved instance info
    if instance.image:
        image = try_assign(glance.images.get, instance.image['id'])
        if image:
            instance._info['image'] = image.name
    instance_flavor = nova.flavors.get(instance.flavor['id'])._info
    instance._info['flavor:name'] = instance_flavor['name']
    instance._info['flavor:vcpus'] = instance_flavor['vcpus']
    instance._info['flavor:ram'] = instance_flavor['ram']
    instance._info['os-extended-volumes:volumes_attached'] = \
        ', '.join(v['id']
                  for v in
                  instance._info['os-extended-volumes:volumes_attached'])
    for az in instance._info['addresses'].keys():
        network_name = "%s network" % az
        network = instance._info['addresses'][az]
        for net in network:
            # Retrieve the device mac to find out the correct tap interface
            if net['addr'] in ip:
                target_mac_device = net['OS-EXT-IPS-MAC:mac_addr']
                break
        output = ', '.join("%s" % net['addr'] for net in network)
        instance._info[network_name] = output
    # Render instance information
    _render_table_instance(instance)
    security_groups = generate_instance_sg_rules_info(neutron, instance.id)
    click.echo(_format_secgroups(security_groups))

    nmap_ports = []
    # Generate recommendation for nmap scan
    for sg in security_groups['security_groups']:
        for rule in sg['security_group_rules']:
            if (rule['direction'] in 'ingress'
               and rule['remote_ip_prefix']
               and rule['remote_ip_prefix'] in '0.0.0.0/0'
               and rule['protocol'] in ['tcp', 'udp']):
                if rule['port_range_min'] == rule['port_range_max']:
                    nmap_ports.append(str(rule['port_range_min']))
                else:
                    nmap_ports.append("%s-%s" % (rule['port_range_min'],
                                                 rule['port_range_max']))
    nmap_command = _recommend_nmap_command(nmap_ports, ip)

    ENABLED_PASSWORD_LOGIN = False
    # Probe the server ssh for password login
    if '22' in nmap_ports:
        vm_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        vm_sock.connect((ip, 22))
        ssh = Session()
        ssh.handshake(vm_sock)
        ssh_authlist = ssh.userauth_list('test')
        click.echo('SSH authentication method list: %s' % ssh_authlist)
        if 'password' in ssh_authlist:
            ENABLED_PASSWORD_LOGIN = True
    # Generate tcpdump
    host_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host_sock.connect((target_host, 22))

    ssh = Session()
    ssh.handshake(host_sock)
    ssh.agent_auth('root')
    channel = ssh.open_session()
    channel.execute("virsh dumpxml %s | grep %s -A3 | grep bridge" %
                    (target_instance_name,
                     target_mac_device))
    size, data = channel.read()
    target_bridge_interface = data.split("'")[1]

    tcpdump_command = "ssh %s 'tcpdump -l -q -i %s not arp and not icmp'" % \
                      (target_host,
                       target_bridge_interface)

    # Print out all recommendation
    click.echo('RECOMMENDATION:')
    if ENABLED_PASSWORD_LOGIN:
        click.echo('* RED FLAG: VM has password login enabled!')
    click.echo("* Discover VM running services by running: %s"
               % nmap_command)
    click.echo("* Discover VM network traffics by running: %s"
               % tcpdump_command)


@aggregate.command(name='move-host')
@click.argument('aggregate')
@click.argument('host')
def aggregate_move_host(aggregate, host):
    """Move HOSTs from an aggregate to another.

    Automatically parse availability zone from aggregate prefix.
    """
    hosts = parse_nodes(host)
    nova = nova_client.Client(2, session=get_session())
    # Find the hosts original aggregates, this is a roundabout way compare
    # to simply using nova.hypervisors.show(), however, there are significant
    # performance issue with using nova.hypervisors.show() at the moment.
    # This aggregates call ends up being significantly faster.
    aggregates = nova.aggregates.list()
    host_ag_mapping = {host: [] for host in hosts}
    target_ag = {}
    for ag in aggregates:
        if aggregate in ag.name:
            target_ag[ag.name] = ag
        for host in hosts:
            if host in ag.hosts:
                host_ag_mapping[host].append(ag)
    # Add and remove hosts
    for host in hosts:
        if not host_ag_mapping[host]:
            click.echo("ERROR: Unable to move host. %s not in any aggregate."
                       % host)
            continue
        target = "%s_%s" % (host_ag_mapping[host][0].name.split('_')[0],
                            aggregate)
        if target not in target_ag:
            click.echo("ERROR: %s not found." % target)
            continue
        for ag in host_ag_mapping[host]:
            nova.aggregates.remove_host(ag, host)
        click.echo("%s removed from [%s]" % (host, ', '.join(ag.name
                                             for ag in host_ag_mapping[host])))
        click.echo("%s added to %s" % (host, target))
        nova.aggregates.add_host(target_ag[target], host)
