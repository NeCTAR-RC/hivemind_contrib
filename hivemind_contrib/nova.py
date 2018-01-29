import collections
import os_client_config
import re
import sys
import time
import urlparse

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fabric.api import task
from prettytable import PrettyTable
from sqlalchemy import Column
from sqlalchemy import create_engine
from sqlalchemy import DateTime
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table

from hivemind import decorators
from hivemind.operations import run
from hivemind.util import current_host
from hivemind_contrib import keystone
from hivemind_contrib.swift import client as swift_client

DEFAULT_AZ = 'melbourne-qh2'
DEFAULT_SECURITY_GROUPS = 'default,openstack-node,puppet-client'

FILE_TYPES = {
    'cloud-config': '#cloud-config',
    'x-shellscript': '#!',
}

metadata = MetaData()
instances_table = Table('instances', metadata,
                        Column('created_at', DateTime()),
                        Column('uuid', String(36)),
                        Column('image_ref', String(255)))


@decorators.configurable('connection')
def db_connect(uri):
    engine = create_engine(uri)
    return engine.connect()


@decorators.configurable('nectar.openstack.client')
def client(url=None, username=None, password=None, tenant=None):
    return os_client_config.make_client('compute', auth_url=url,
                                        username=username, password=password,
                                        project_name=tenant)


def list_services():
    output = run("nova-manage service list 2>/dev/null")
    services = []
    header = None
    for line in output.split("\n"):
        if not header:
            header = [l.lower() for l in line.split()]
            continue
        services.append(dict(zip(header, line.split())))
    return services


def host_services(host=None):
    if not host:
        host = current_host()
    return [service for service in list_services()
            if service["host"] == host]


@decorators.only_for("nova-node", "nova-controller")
def disable_host_services(host=None):
    if not host:
        host = current_host()
    for service in host_services(host):
        run("nova-manage service disable --host %s --service %s" %
            (service["host"], service["binary"]))


@decorators.only_for("nova-node", "nova-controller")
def enable_host_services(host=None):
    if not host:
        host = current_host()
    for service in host_services(host):
        run("nova-manage service enable --host %s --service %s" %
            (service["host"], service["binary"]))


def get_flavor_id(client, flavor_name):
    flavors = client.flavors.list()
    for flavor in flavors:
        if flavor.name == flavor_name:
            return flavor.id
    raise Exception("Can't find flavor %s" % flavor_name)


def get_flavor(client, flavor_id):
    """Get a flavor ID"""
    return client.flavors.get(flavor_id)


def wait_for(func, error_message):
    for i in xrange(60):
        ret = func()
        if ret:
            return ret
        time.sleep(1)
    raise Exception(error_message)


def server_address(client, id):
    server = client.servers.get(id)
    if not server.addresses:
        return None
    for name, addresses in server.addresses.items():
        for address in addresses:
            if address.get('addr'):
                return address['addr']


def all_servers(client, zone=None, host=None, status=None, ip=None,
                image=None, project=None, user=None, limit=None):
    marker = None
    opts = {}
    opts["all_tenants"] = True
    if status:
        opts['status'] = status
    if limit:
        opts['limit'] = limit
    if image:
        opts['image'] = image
    if project:
        opts['tenant_id'] = project
    if user:
        opts['user_id'] = keystone.get_user(keystone.client(), user).id

    hosts_list = parse_nodes(host) if host else None
    az_list = parse_nodes(zone) if zone else None
    ip_list = parse_nodes(ip) if ip else None

    inst = []
    if host:
        for host in hosts_list:
            opts['host'] = host
            start_time0 = time.time()
            instances = client.servers.list(search_opts=opts)
            print("===== It takes %s seconds for host filtering instance list with total %s instances" % ((time.time() - start_time0), len(instances)))
            if not instances:
                continue
            instances = filter(lambda x: match_availability_zone(x, az_list),
                               instances)
            instances = filter(lambda x: match_ip_address(x, ip_list),
                               instances)
            print("===== MATCH IP/AZ: %s instances returned in  %s seconds" % (len(instances), time.time() - start_time0))
            inst.extend(instances)
        return inst
    else:
        while True:
            if marker:
                opts['marker'] = marker
            start_time = time.time()
            instances = client.servers.list(search_opts=opts)
            print("===== It takes %s second for ALL instance list with total %s instances" % (time.time() - start_time, len(instances)))
            if not instances:
                return inst
            marker = instances[-1].id
            instances = filter(lambda x: match_availability_zone(x, az_list),
                               instances)
            instances = filter(lambda x: match_ip_address(x, ip_list),
                               instances)
            if not instances:
                continue
            inst.extend(instances)
            print("===== MATCH IP/AZ: %s instances returned in %s seconds" % (len(instances), time.time() - start_time))


def match_availability_zone(server, az=None):
    if az:
        if getattr(server, "OS-EXT-AZ:availability_zone") not in az:
            return False
    return True


def match_ip_address(server, ips):
    if not ips:
        return True
    for ip in ips:
        if ip == server.accessIPv4 or ip == server.accessIPv6:
            return True
        if any(map(lambda a: any(map(lambda aa: ip in aa['addr'], a)),
                        server.addresses.values())):
            return True
    return False


def extract_server_info(server):
    server_info = collections.defaultdict(dict)
    try:
        server_info['id'] = server.id
        server_info['name'] = server.name
        server_info['status'] = server.status
        server_info['image'] = server.image['id']
        server_info['flavor'] = server.flavor['id']
        server_info['host'] = getattr(server, "OS-EXT-SRV-ATTR:host")
        server_info['zone'] = getattr(server, "OS-EXT-AZ:availability_zone")

        # handle some tier2 services which using "global" service user/project
        if server.metadata and 'user_id' in server.metadata.keys()\
            and 'project_id' in server.metadata.keys():
            server_info['user'] = server.metadata['user_id']
            server_info['project'] = server.metadata['project_id']
        else:
            server_info['user'] = server.user_id
            server_info['project'] = server.tenant_id

        server_info['project_name'] =\
                keystone.get_project(keystone.client(),
                                     server_info['project']).name

        server_info['accessIPv4'] = extract_ip(server)
        user = keystone.get_user(keystone.client(), server_info['user'])

        # handle instaces created by jenkins/tempest etc.
        if user.email:
            server_info['email'], server_info['fullname']\
                    = user.email, user.full_name
        else:
            server_info['email'], server_info['fullname']\
                    = user.name, None
    except KeyError as e:
        raise type(e)(e.message + ' missing in context: %s' % server.to_dict())

    return server_info


def extract_ip(server):
    addresses = set()
    if server.accessIPv4:
        addresses.add(server.accessIPv4)
    elif server.accessIPv6:
        addresses.add(server.accessIPv6)

    for address in server.addresses.values():
        for addr in address:
            if addr['addr']:
                addresses.add(addr['addr'])
    return list(addresses)


def parse_dash(range_str):
    """Unpack the dash syntax into a set of number"""
    hosts = range_str.split("-")
    leading = len(hosts[0])
    range_list = range(int(hosts[0]), int(hosts[1]) + 1) if len(hosts) > 1 \
                 else [range_str]
    return map(lambda x: str(x).zfill(leading), range_list)


def parse_nodes(nodes):
    """Parse list syntax (eg. qh2-rcc[01-10,13])"""

    # Parse qh2-rcc5,qh2-rcc6,qh2-rcc7 syntax
    nodes = re.split(r",\s*(?![^\[\]]*\])", nodes)

    if len(nodes) > 1:
        nodes = set(host for hosts in nodes for host in parse_nodes(hosts))
    else:
        # Parse qh2-rcc[112-114,115] syntax
        match = re.search(r"(.*?)\[(.*?)\](.*)", nodes[0])
        if match:
            host_ranges = [host for hosts in parse_nodes(match.group(2))
                           for host in parse_dash(hosts)]
            nodes = set("%s%s%s" % (match.group(1), host, match.group(3))
                        for host in host_ranges)
    return nodes


def combine_files(file_contents):
    combined_message = MIMEMultipart()
    for i, contents in enumerate(file_contents):
        for content_type, start in FILE_TYPES.items():
            if contents.startswith(start):
                break
        else:
            raise Exception("Can't find handler for '%s'" %
                            contents.split('\n', 1)[0])

        sub_message = MIMEText(contents, content_type,
                               sys.getdefaultencoding())
        sub_message.add_header('Content-Disposition',
                               'attachment; filename="file-%s"' % i)
        combined_message.attach(sub_message)
    return combined_message


def file_contents(filenames):
    for filename in filenames:
        url = urlparse.urlsplit(filename)
        if url.scheme == 'swift':
            resp = swift_client().get_object(url.netloc, url.path.strip('/'))
            yield resp[1]
        elif not url.scheme:
            with open(url.path) as fh:
                yield fh.read()
        else:
            raise ValueError('Unrecognised url scheme %s' % url.scheme)


@task
@decorators.verbose
def boot(name, key_name=None, image_id=None, flavor='m1.small',
         security_groups=DEFAULT_SECURITY_GROUPS,
         networks=[], userdata=[], availability_zone=DEFAULT_AZ):
    """Boot a new server.

       :param str name: The name you want to give the VM.
       :param str keyname: Key name of keypair that should be used.
       :param str flavor: Name or ID of flavor,
       :param str security_groups: Comma separated list of security
         group names.
       :param list userdata: User data file to pass to be exposed by
         the metadata server.
       :param list networks: A list of networks that the VM should
         connect to. net-id: attach NIC to network with this UUID
         (required if no port-id), v4-fixed-ip: IPv4 fixed address
         for NIC (optional), port-id: attach NIC to port with this
         UUID (required if no net-id).
         (e.g. net-id=<net-uuid>;v4-fixed-ip=<ip-addr>;port-id=<port-uuid>,...)
       :param str availability_zone: The availability zone for
         instance placement.
       :param choices ubuntu: The version of ubuntu you would like to use.

    """
    nova = client()

    flavor_id = get_flavor_id(nova, flavor)

    nics = []
    for net in networks:
        nics.append({})
        for option in net.split(';'):
            key, value = option.split('=')
            nics[-1][key] = value

    resp = nova.servers.create(
        name=name,
        flavor=flavor_id,
        security_groups=security_groups.split(','),
        userdata=str(combine_files(file_contents(userdata))),
        image=image_id,
        nics=nics,
        availability_zone=availability_zone,
        key_name=key_name)

    server_id = resp.id
    ip_address = wait_for(lambda: server_address(nova, resp.id),
                          "Server never got an IP address.")
    print(server_id)
    print(ip_address)


@task
@decorators.verbose
def list_host_aggregates(availability_zone, hostname=[]):
    """Prints a pretty table of hosts in for each aggregate in AZ

       :param str availability_zone: The availability zone that the aggregates
         are in
       :param str hostname: Only display hostname in table. Use multiple times
         for more then one host
    """

    nova = client()

    # filters for aggregates in availability_zone
    aggregate_list = nova.aggregates.list()
    aggregates = []
    for aggregate in aggregate_list:
        if aggregate.availability_zone == availability_zone:
            aggregates.append(aggregate)

    hosts = []
    # loads hosts from aggregates if not specified
    if not hostname:
        for aggregate in aggregates:
            hosts.extend(aggregate.hosts)
    else:
        hosts = hostname

    # unique hosts
    hosts = list(set(hosts))
    hosts.sort()

    # builds table
    header = ["Aggregates"] + hosts
    table = PrettyTable(header)
    table.align["Aggregates"] = 'l'
    aggregates.sort()
    for aggregate in aggregates:
        row = [aggregate.name]
        for host in hosts:
            if host in aggregate.hosts:
                row.append("X")
            else:
                row.append("")
        table.add_row(row)

    print(table)


@task
@decorators.verbose
def list_instances(zone=None, nodes=None, project=None, user=None, status="ACTIVE",
                   ip=None, image=None, limit=None):
    novaclient = client()
    result = all_servers(novaclient, zone=zone, host=nodes, status=status,
                         ip=ip, image=image, project=project, user=user,
                         limit=limit)
    if not result:
        print("No instances found!")
        sys.exit(0)
    result = map(extract_server_info, result)
    header = None
    for inst in result:
        if not header:
            header = inst.keys()
            table = PrettyTable(header)
        table.add_row(inst.values())
    print(table)
    print("number of instances:", len(result))
    return result
