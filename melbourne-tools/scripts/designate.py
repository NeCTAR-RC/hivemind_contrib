#!/usr/bin/env python
#
# Description: Swiss-knife for working with DNS
# Example usage:
# ./designate.py create oob.hpc.unimelb.edu.au. spartan-gpgpu069 --type A
#   --record 172.26.1.212
# ./designate.py free '172.26.0.0/23'
# ./designate.py delete oob.hpc.unimelb.edu.au. spartan-gpgpu071
#

import click
from designateclient.v2 import client as designate_client
from difflib import SequenceMatcher
import ipaddress
from prettytable import PrettyTable
from utils import c
from utils import get_session
from utils import try_assign

# Adjust the sensitivity of group mode matching
MATCHING_THRESHOLD = 5


def _find_leading_pos(records, lead_ip):
    """Find the leading position from the IP host, if not found return 0."""
    if lead_ip is not None:
        for idx, record in enumerate(records):
            if record['ip'] == lead_ip:
                return idx
    return 0


def _list_short(records, limit=None, lead_ip=None):
    """Just list the list of available IP addresses."""
    lead_pos = _find_leading_pos(records, lead_ip)

    # Construct a table from leading IP onward
    table = [record['ip']
             for record in records[lead_pos:]
             if 'type' not in record]

    if limit is None:
        for record in table:
            click.echo(record)
    else:
        for record in table[:limit]:
            click.echo(record)
        return


def _list_group(table, records, lead_ip=None):
    """List IP address is group mode."""
    lead_pos = _find_leading_pos(records, lead_ip)

    prev = records[lead_pos]
    matching = None
    rep = 0
    # Handle for the first record
    pr = ','.join(prev['records'])
    pip = prev['ip']
    if 'type' not in prev:
        pr = click.style(pr, fg=c.SUCCESS)
        pip = click.style(pip, fg=c.SUCCESS)
    table.add_row([pip, pr])
    # Comparing similarity and merge common elements
    for record in records[lead_pos+1:]:
        rr = ','.join(record['records'])
        pr = ','.join(prev['records'])
        rip = record['ip']
        pip = prev['ip']
        if not matching:
            match = SequenceMatcher(None,
                                    rr,
                                    pr)
            match = match.find_longest_match(0, len(rr), 0, len(pr))
            matching = rr[match.a: match.a + match.size]
            # If the size of match below THRESHOLD, consider it different
            if match.size < MATCHING_THRESHOLD:
                if 'type' not in record:
                    rip = click.style(rip, c.SUCCESS)
                    rr = click.style(rr, c.SUCCESS)
                table.add_row([rip, rr])
                matching = None
        else:
            if matching not in rr:
                dot_color = False
                if 'type' not in prev:
                    pip = click.style(pip, c.SUCCESS)
                    pr = click.style(pr, c.SUCCESS)
                    dot_color = True
                if 'type' not in record:
                    rip = click.style(rip, c.SUCCESS)
                    rr = click.style(rr, c.SUCCESS)
                if rep > 0:
                    if dot_color:
                        dot = click.style('...', c.SUCCESS)
                        table.add_row([dot, dot])
                    else:
                        table.add_row(['...', '...'])
                table.add_row([pip, pr])
                table.add_row([rip, rr])
                matching = None
                rep = 0
            else:
                rep += 1
        prev = record
    # Handle the case where last record is still matching
    last = records[-1]
    lr = ','.join(last['records'])
    lip = last['ip']
    if 'type' not in last:
        lr = click.style(lr, c.SUCCESS)
        lip = click.style(lip, c.SUCCESS)
    if matching and matching in lr:
        table.add_row(['...', '...'])
        table.add_row([lip, lr])


def _list_long(table, records, lead_ip=None):
    """List all record mode."""
    lead_pos = _find_leading_pos(records, lead_ip)

    for record in records[lead_pos:]:
        ip = record['ip']
        rr = ','.join(record['records'])
        if 'type' not in record:
            ip = click.style(ip, c.SUCCESS)
            rr = click.style(rr, c.SUCCESS)
        table.add_row([ip, rr])


def _list(records, display, limit=None, lead_ip=None):
    """Pretty print records, skip over any IP before lead IP address."""
    if display == 0:
        _list_short(records, limit, lead_ip)
    else:
        table = PrettyTable()
        table.field_names = ['Address', 'Hostname']
        table.align = 'l'
        list_mode = {1: _list_group, 2: _list_long}
        list_mode[display](table, records, lead_ip)
        click.echo(table)


def _show(record):
    """Pretty print a DNS record entry."""
    table = PrettyTable()
    table.field_names = ['Field', 'Value']
    table.align = 'l'
    table.add_row(['action', record['action']])
    table.add_row(['created_at', record['created_at']])
    table.add_row(['description', record['description']])
    table.add_row(['id', record['id']])
    table.add_row(['name', record['name']])
    table.add_row(['project_id', record['project_id']])
    table.add_row(['record', ','.join(record['records'])])
    table.add_row(['status', record['status']])
    table.add_row(['ttl', record['ttl']])
    table.add_row(['type', record['type']])
    table.add_row(['updated_at', record['updated_at']])
    table.add_row(['version', record['version']])
    table.add_row(['zone_id', record['zone_id']])
    table.add_row(['zone_name', record['zone_name']])
    click.echo(table)


def _get_ptr_name_zone(ip_address):
    """Get the PTR name and zone suitable for designate from IP_ADDRESS."""
    name = "%s." % ip_address.reverse_pointer
    zone = '.'.join(name.split('.')[1:])
    return (name, zone)


def _make_record_update_data(record, description=None, ttl=None):
    """Make the record update data."""
    update_data = {'records': [record]}
    if description is not None:
        update_data['description'] = description
    if ttl is not None:
        update_data['ttl'] = ttl
    return update_data


def _create_CNAME_record(client, zone, name, record, description=None,
                         ttl=None, yes_prompt=False):
    """Create CNAME record IPv4."""
    record_name = "%s.%s" % (name, zone)
    # Check if entry exist
    entry = try_assign(client.recordsets.get, zone, record_name)

    if entry is not None:
        _show(entry)
        if yes_prompt or (click.confirm("Entry existed. Update entry instead?",
                          abort=True)):
            click.echo("Updating CNAME record for %s" % record_name)
            update_data = _make_record_update_data(record, description, ttl)
            _show(client.recordsets.update(zone, record_name, update_data))
    else:
        click.echo("Creating CNAME record for %s" % record_name)
        _show(client.recordsets.create(zone, record_name, 'CNAME',
                                       [record], description, ttl))


def _create_A_and_PTR_record(client, zone, name, record, description=None,
                             ttl=None, yes_prompt=False):
    """Create A and PTR record IPv4."""
    record_name = "%s.%s" % (name, zone)
    # Check if entry exist
    entry = try_assign(client.recordsets.get, zone, record_name)
    # If it exists
    if entry is not None:
        _show(entry)
        if yes_prompt or (click.confirm("Entry existed. Update entry instead?",
                          abort=True)):
            click.echo("Updating A record for %s" % record_name)
            old_record_ip = ipaddress.ip_address(entry['records'][0])
            old_ptr_record_name, old_ptr_zone = \
                _get_ptr_name_zone(old_record_ip)
            update_data = _make_record_update_data(record.exploded,
                                                   description, ttl)
            _show(client.recordsets.update(zone, record_name, update_data))
            ptr_entry = try_assign(client.recordsets.get, old_ptr_zone,
                                   old_ptr_record_name)
            if ptr_entry is not None:
                _show(ptr_entry)
                if yes_prompt or (click.confirm("Delete old PTR record?",
                                  abort=True)):
                    click.echo("Deleting PTR record for %s" %
                               old_ptr_record_name)
                    _show(client.recordsets.delete(old_ptr_zone,
                                                   old_ptr_record_name))

    else:
        click.echo("Creating A record for %s" % record_name)
        _show(client.recordsets.create(zone, record_name, 'A',
                                       [record.exploded],
                                       description, ttl))

    ptr_record_name, ptr_zone = _get_ptr_name_zone(record)
    ptr_entry = try_assign(client.recordsets.get, ptr_zone, ptr_record_name)

    if ptr_entry is not None:
        _show(ptr_entry)
        if yes_prompt or (click.confirm("Entry existed. Update entry instead?",
                          abort=True)):
            click.echo("Updating PTR record for %s" % ptr_record_name)
            update_data = _make_record_update_data(record_name, description,
                                                   ttl)
            _show(client.recordsets.update(ptr_zone, ptr_record_name,
                                           update_data))
    else:
        click.echo("Creating PTR record for %s" % ptr_record_name)
        _show(client.recordsets.create(ptr_zone, ptr_record_name,
                                       'PTR', [record_name],
                                       description, ttl))


def _generate_free_entry(addr, records_dict):
    """Generate the entry record for display."""
    addr = u'%s' % addr
    if addr in records_dict:
        records_dict[addr]['ip'] = addr
        return records_dict[addr]
    else:
        return {
            'ip': addr,
            'records': ['No DNS record found']
        }


def _find_free_entries(client, network, zone):
    """Find the free entries with NETWORK in the ZONE."""
    hosts = network.hosts()
    recordsets = client.recordsets.list(zone)
    # Format the recordsets and take only PTR records
    records_dict = {'.'.join(record['name'][:-14].split('.')[::-1]):
                    record for record in recordsets
                    if record['type'] in 'PTR'}
    records = []
    # Enumerate subnet  and find any entries
    for host in hosts:
        records.append(_generate_free_entry(host, records_dict))

    # Include the network and broadcast address
    records.insert(0, _generate_free_entry(network.network_address,
                                           records_dict))
    records.append(_generate_free_entry(network.broadcast_address,
                                        records_dict))
    return records


@click.group()
def cli():
    """Swiss-knife for designate records management."""
    pass


@cli.command()
@click.argument('zone')
@click.argument('name')
@click.option('--type', required=True, help='The entry type')
@click.option('--record', required=True, type=str,
              help='The record of the DNS entry')
@click.option('--description', help='The description of the entry')
@click.option('--ttl', help='The TTL of the entry')
@click.option('--yes', is_flag=True,
              help='Say YES to all update/delete prompt (DANGEROUS)')
def create(zone, name, type, record, description, ttl, yes):
    """Create a new designate NAME record in the fully qualified ZONE."""
    ds = designate_client.Client(session=get_session())

    if type in 'A':
        # Validate the record IP address
        ip_address = try_assign(ipaddress.ip_address, record, exit=True)
        _create_A_and_PTR_record(ds, zone, name, ip_address, description,
                                 ttl, yes)
    elif type in 'CNAME':
        _create_CNAME_record(ds, zone, name, record, description, ttl, yes)
    else:
        click.echo("Type")


@cli.command()
@click.argument('zone')
@click.argument('name')
@click.option('--yes', is_flag=True,
              help='Say YES to all delete prompt (DANGEROUS)')
def delete(zone, name, yes):
    """Delete the A record and PTR reverse record."""
    ds = designate_client.Client(session=get_session())

    # Get the record name
    record_name = "%s.%s" % (name, zone)
    record = try_assign(ds.recordsets.get, zone, record_name, exit=True)

    # Delete A record
    if record['type'] in 'A':
        _show(record)
        if (yes or
            click.confirm("Are you sure you want to delete this record?",
                          abort=True)):
            click.echo("Deleting A record for %s" % record_name)
            old_record_ip = ipaddress.ip_address(record['records'][0])
            old_ptr_record_name, old_ptr_zone = \
                _get_ptr_name_zone(old_record_ip)

            _show(ds.recordsets.delete(zone, record_name))

            ptr_record = try_assign(ds.recordsets.get, old_ptr_zone,
                                    old_ptr_record_name)
            if ptr_record is not None:
                _show(ptr_record)
                if (yes or
                    click.confirm("Do you want to delete PTR record?",
                                  abort=True)):
                    print("Deleting PTR record for %s" %
                          old_ptr_record_name)
                    _show(ds.recordsets.delete(old_ptr_zone,
                                               old_ptr_record_name))
    # Delete CNAME record
    elif record['type'] in 'CNAME':
        _show(record)
        if (yes or
            click.confirm("Are you sure you want to delete this record?",
                          abort=True)):
            click.echo("Deleting CNAME record for %s" % record_name)
            _show(ds.recordsets.delete(zone, record_name))


@cli.command()
@click.argument('network', type=str)
@click.option('--short', 'display', flag_value=0,
              help='Only list the available IP addresses')
@click.option('--limit', type=int,
              help='Only list LIMIT number of available IPs for --short mode')
@click.option('--group', 'display', flag_value=1,
              help='Skip similar records when listing')
@click.option('--long', 'display', flag_value=2, default=True,
              help='Show all records (DEFAULT)')
def free(network, display, limit):
    """Display defined PTR record for the given CIDR range."""
    ds = designate_client.Client(session=get_session())

    # Save the raw input of the network
    raw_network = network
    network = try_assign(ipaddress.ip_network,
                         network,
                         strict=False,
                         exit=True)

    # Get the lead IP address to skip of the network
    lead_ip_address = raw_network.split('/')[0]

    # Break the network into /24 chunks for PTR search
    # if NETWORK prefix < 24
    if (network.prefixlen < 24):
        network = network.subnets(new_prefix=24)
    else:
        network = [network]
    # Search the subnet for data
    records = []
    for net in network:
        net_ptr, net_zone = _get_ptr_name_zone(net)
        records.extend(_find_free_entries(ds, net, net_zone))
    _list(records, display, limit, lead_ip_address)
