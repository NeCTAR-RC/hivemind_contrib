import collections
import dateutil.parser
import re
import sys
import time
from urllib import parse

from novaclient import client as nova_client

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
from hivemind.decorators import Spinner
from hivemind.operations import run
from hivemind.util import current_host
from hivemind_contrib import keystone
from hivemind_contrib.swift import client as swift_client

DEFAULT_AZ = 'melbourne-qh2'
DEFAULT_SECURITY_GROUPS = 'default,openstack-node,puppet-client'

FILE_TYPES = {
    'cloud-config': '#cloud-config',
    'x-shellscript': '#!',
    'jinja2': '## template: jinja',
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
def client(url=None, username=None, password=None, tenant=None, version='2.1'):
    sess = keystone.get_session(username=username, password=password,
                                tenant_name=tenant, auth_url=url)
    return nova_client.Client(version, session=sess)


def list_services():
    output = run("nova-manage service list 2>/dev/null")
    services = []
    header = None
    for line in output.split("\n"):
        if not header:
            header = [ln.lower() for ln in line.split()]
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


def list_instance_actions(client, instance_id):
    return client.instance_action.list(instance_id)


def get_instance_action(client, instance_id, req_id):
    return client.instance_action.get(instance_id, req_id)


def wait_for(func, error_message):
    for i in range(90):
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


@Spinner
def all_servers(client, zone=None, host=None, status=None, ip=None,
                image=None, project=None, user=None, limit=None,
                changes_since=None):
    print("\nListing the instances... ", end="")
    marker = None
    opts = {}
    opts["all_tenants"] = True
    if status:
        opts['status'] = status
    if limit:
        opts['limit'] = limit
    if image:
        opts['image'] = image
    if changes_since:
        opts['changes-since'] = changes_since
    if project:
        try:
            opts['tenant_id'] = keystone.get_project(
                keystone.client(), project, use_cache=True).id
        except Exception:
            sys.exit(1)
    if user:
        try:
            opts['user_id'] = keystone.get_user(
                keystone.client(), user, use_cache=True).id
        except Exception:
            sys.exit(1)

    host_list = parse_nodes(host) if host else None
    az_list = parse_nodes(zone) if zone else None
    ip_list = parse_nodes(ip) if ip else None

    # When using all the searching opts other than project or user,
    # trove instances will be returned by default via nova list api.
    # But they will not when search_opts contain project or user.
    # In order to include them, searching all the instances under
    # project "trove" and filtering them by the instance metadata.
    if project or user:
        inst = _search_trove_instances(client, opts)
    else:
        inst = []

    if host_list:
        for host in host_list:
            opts['host'] = host
            instances = client.servers.list(search_opts=opts)
            if not instances:
                continue
            instances = filter(lambda x: _match_availability_zone(x, az_list),
                               instances)
            instances = filter(lambda x: _match_ip_address(x, ip_list),
                               instances)
            inst.extend(instances)
            if limit and len(inst) >= int(limit):
                break
        return inst
    else:
        while True:
            if marker:
                opts['marker'] = marker
            instances = client.servers.list(search_opts=opts)
            if not instances:
                return inst
            # for some instances stuck in build phase, servers.list api
            # will always return the marker instance. Add old marker and
            # new marker comparision to avoid the dead loop
            marker_new = instances[-1].id
            if marker == marker_new:
                return inst
            marker = marker_new
            instances = filter(lambda x: _match_availability_zone(x, az_list),
                               instances)
            instances = filter(lambda x: _match_ip_address(x, ip_list),
                               instances)
            if not instances:
                continue
            inst.extend(instances)
            if limit and len(inst) >= int(limit):
                return inst


def _search_trove_instances(client, opts):
    # keep the proj/user from searching opts
    proj_id = opts.get('tenant_id', None)
    user_id = opts.get('user_id', None)

    # trove instances will be launched by global trove project
    trove_opts = opts.copy()
    trove_opts.pop('user_id', None)
    trove_opts['tenant_id'] = keystone.get_project(
        keystone.client(), 'trove', use_cache=True).id
    trove_instances = client.servers.list(search_opts=trove_opts)
    trove_instances = [instance for instance in trove_instances
                       if _match_proj_user(instance, proj_id, user_id)]
    return trove_instances


def _match_proj_user(server, proj_id=None, user_id=None):
    # server.metadata will return dict containing user's projectid and userid
    if proj_id:
        if getattr(server, 'metadata').get("project_id") != proj_id:
            return False
    if user_id:
        if getattr(server, 'metadata').get("user_id") != user_id:
            return False
    return True


def _match_availability_zone(server, az=None):
    if az:
        if getattr(server, "OS-EXT-AZ:availability_zone") not in az:
            return False
    return True


def _match_ip_address(server, ips):
    if not ips:
        return True
    for ip in ips:
        if any(map(lambda a: any(map(lambda aa: ip in aa['addr'], a)),
                        server.addresses.values())):
            return True
    return False


def extract_server_info(server, ksclient):
    server_info = collections.defaultdict(dict)
    try:
        server_info['id'] = server.id
        server_info['name'] = server.name
        server_info['status'] = server.status

        server_info['flavor'] = server.flavor['id']
        server_info['host'] = getattr(server, "OS-EXT-SRV-ATTR:host")
        server_info['zone'] = getattr(server, "OS-EXT-AZ:availability_zone")

        # handle vms which are not booted from glance images
        server_image = getattr(server, "image", None)
        if server_image:
            server_info['image'] = server_image.get("id", None)
        else:
            server_info['image'] = None

        # handle some tier2 services which using "global" service user/project
        if server.metadata and 'user_id' in server.metadata.keys()\
            and 'project_id' in server.metadata.keys():
            server_info['user'] = server.metadata['user_id']
            server_info['project'] = server.metadata['project_id']
        else:
            server_info['user'] = server.user_id
            server_info['project'] = server.tenant_id

        server_info['addresses'] = _extract_ip(server)

        server_info['project_name'] = keystone.get_project(
            ksclient, server_info['project'], use_cache=True).name
        user = keystone.get_user(
            ksclient, server_info['user'], use_cache=True)

        # handle instaces created by jenkins/tempest and users without fullname
        # set disabled user's email/fullname as None as it should be ruled out
        if not user.enabled:
            server_info['email'], server_info['fullname'] = None, None
        elif getattr(user, 'email', None):
            server_info['email'], server_info['fullname']\
                    = user.email, getattr(user, 'full_name', None)
        else:
            server_info['email'], server_info['fullname']\
                    = user.name, None
    except KeyError as e:
        raise type(e)(e.message + ' missing in context: %s' % server.to_dict())

    return server_info


def _extract_ip(server):
    addresses = set()

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
        url = parse.urlsplit(filename)
        if url.scheme == 'swift':
            resp = swift_client().get_object(url.netloc, url.path.strip('/'))
            yield resp[1]
        elif not url.scheme:
            with open(url.path) as fh:
                yield fh.read()
        else:
            raise ValueError('Unrecognised url scheme %s' % url.scheme)


def _scenario_compute_failure(novaclient, server, changes_since):
    try:
        last_action = list_instance_actions(novaclient, server['id'])[0]
        if _normalize_time(last_action.start_time) >= _normalize_time(
            changes_since) and last_action.action == "stop" \
                           and not last_action.project_id \
                           and not last_action.user_id:
            return True
        else:
            return False
    except Exception as e:
        # bypass the failure when instance action call return failures
        print("\nException %s with server %s" % (e, server['id']))
        return False


def _normalize_time(string):
    t1 = dateutil.parser.parse(string)
    t2 = t1.replace(tzinfo = dateutil.tz.tzutc())
    return t2


@Spinner
def extract_servers_info(servers, ksclient=None):
    print("\nExtracting instances information... ", end="")
    if ksclient is None:
        ksclient = keystone.client()
    return [extract_server_info(server, ksclient=ksclient)
            for server in servers]


@Spinner
def match_scenario(servers, func, novaclient, changes_since):
    print("\nFiltering by scenario checking... ", end="")
    return [server for server in servers if func(novaclient, server,
                                                 changes_since)]


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
def list_instances(zone=None, nodes=None, project=None, user=None,
                   status="ACTIVE", ip=None, image=None, limit=None,
                   changes_since=None, scenario=None):
    """Prints a pretty table of instances based on specific conditions

       :param str zone: Availability zone or availability zone range
            that the instances are in, e.g. az[1-4,9]
       :param str nodes: Compute host name or host neme range that the
            instances are in, e.g. cc[2-3,5]
       :param str project: Project name or id that the instances belong to
       :param str user: User name or id that the instances belong to
       :param str status: Instances status. Use 'ALL' to list all instances
       :param str ip: Ip address or ip address range that instances are in,
            e.g. 192.168.122.[124-127]
       :param str image: Image id that the instances are launched based on
       :param str limit: Number of returned instances
       :param str changes_since: List only instances changed after a certain
            point of time. The provided time should be an ISO 8061 formatted
            time. e.g. 2016-03-04T06:27:59Z
       :param str scenario: List only instances which match with specific
            scenario checking, available ones are ["compute_failure"]
    """
    novaclient = client()
    if status == 'ALL':
        status = None
    result = all_servers(novaclient, zone=zone, host=nodes, status=status,
                         ip=ip, image=image, project=project, user=user,
                         limit=limit, changes_since=changes_since)
    if not result:
        print("No instances found!")
        sys.exit(0)
    result = extract_servers_info(result, keystone.client())

    if scenario:
        func = globals()["_scenario_" + scenario]
        result = match_scenario(result, func, novaclient, changes_since)
        if not result:
            print("No %s instances found!" % scenario)
            sys.exit(0)

    print("\n")
    header = None
    for inst in result:
        if not header:
            header = inst.keys()
            table = PrettyTable(header)
        table.add_row(inst.values())
    print(table)
    print("number of instances:", len(result))
    return result
