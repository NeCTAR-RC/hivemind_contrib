import collections
import csv
import datetime
import logging
import os
import requests
import sys
import traceback

from fabric.api import task
from prettytable import PrettyTable

import hivemind_contrib.keystone as hm_keystone
import hivemind_contrib.nova as hm_nova

from hivemind.decorators import verbose


def csv_output(headings, rows, filename=None):
    if filename is None:
        fp = sys.stdout
    else:
        fp = open(filename, 'wb')
    csv_output = csv.writer(
        fp, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL
    )
    csv_output.writerow(headings)
    for row in rows:
        csv_output.writerow(map(lambda x: str(x).encode('utf-8'), row))
    if filename is not None:
        fp.close()


def pretty_output(headings, rows, filename=None):
    if filename is None:
        fp = sys.stdout
    else:
        fp = open(filename, 'wb')
    pp = PrettyTable(headings)
    for r in rows:
        pp.add_row(r)
    fp.write(str(pp) + '\n')


def ssl_warnings(enabled=False):
    if not enabled:
        logging.captureWarnings(True)


@task
@verbose
def allocation_homes(csv=False, filename=None, sslwarnings=False):
    """Get the allocation_homes for all projects. If this
    metadata field is not set in keystone (see keystone hivemind
    commands), the value reported is the email domains for all
    tenant managers belonging to this project.
    """
    ssl_warnings(enabled=sslwarnings)
    keystone = hm_keystone.client()
    all_users = map(lambda x: x.to_dict(), keystone.users.list())
    email_dict = {
        x['id']: x['email'].split("@")[-1]
        for x in all_users
        if 'email' in x and x['email'] is not None
    }
    projects = keystone.projects.list()
    managers = collections.defaultdict(list)
    for user_role in keystone.role_assignments.list(role=14):
        if 'project' in user_role.scope:
            managers[user_role.scope['project']['id']].append(
                user_role.user['id']
            )
    headings = ["Tenant ID", "Allocation Home(s)"]
    records = []
    for proj in projects:
        if "allocation_home" in proj.to_dict():
            records.append([proj.id, proj.allocation_home])
        else:
            if len(managers[proj.id]) == 0:
                continue
            institutions = set()
            for tm in managers[proj.id]:
                if tm in email_dict:
                    institutions.add(email_dict[tm])
            records.append([proj.id, ",".join(institutions)])
    if csv:
        csv_output(headings, records, filename=filename)
    else:
        pretty_output(headings, records, filename=filename)


@task
@verbose
def allocation_managers(csv=False, filename=None, sslwarnings=False):
    """Get the allocation manager emails for all projects."""
    ssl_warnings(enabled=sslwarnings)
    keystone = hm_keystone.client()
    all_users = map(lambda x: x.to_dict(), keystone.users.list())
    email_dict = {
        x['id']: x['email']
        for x in all_users
        if 'email' in x and x['email'] is not None
    }
    projects = keystone.projects.list()
    managers = collections.defaultdict(list)
    for user_role in keystone.role_assignments.list(role=14):
        if 'project' in user_role.scope:
            managers[user_role.scope['project']['id']].append(
                user_role.user['id']
            )
    headings = ["Tenant ID", "Manager email(s)"]
    records = []
    for proj in projects:
        if len(managers[proj.id]) == 0:
            continue
        emails = set()
        for tm in managers[proj.id]:
            if tm in email_dict:
                emails.add(email_dict[tm])
        records.append([proj.id, ",".join(emails)])
    if csv:
        csv_output(headings, records, filename=filename)
    else:
        pretty_output(headings, records, filename=filename)


@task
@verbose
def get_project_usage_csv(
    start_date, end_date, filename=None, sslwarnings=False
):
    """Get accumulated instance usage statistics for all projects.
    Date strings should be ISO 8601 to minute precision
    without timezone information.
    """
    ssl_warnings(enabled=sslwarnings)
    start = datetime.datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    end = datetime.datetime.strptime(end_date, "%Y-%m-%dT%H:%M")
    keystone = hm_keystone.client()
    nova = hm_nova.client()

    tenants = {x.id: x for x in keystone.projects.list()}
    headings = [
        "Tenant ID",
        "Tenant Name",
        "Instance count",
        "Instance hours",
        "vCPU hours",
        "Memory Hours (MB)",
        "Disk hours (GB)",
    ]
    usage = map(
        lambda u: [
            u.tenant_id,
            tenants[u.tenant_id].name if u.tenant_id in tenants else None,
            len(u.server_usages),
            u.total_hours,
            u.total_vcpus_usage,
            u.total_memory_mb_usage,
            u.total_local_gb_usage,
        ],
        nova.usage.list(start, end, detailed=True),
    )
    csv_output(headings, usage, filename=filename)


@task
@verbose
def get_instance_usage_csv(
    start_date, end_date, tenant=None, filename=None, sslwarnings=False
):
    """Get individual instance usage for all projects, including tenant and
    availability zones.  Date strings should be ISO 8601 to minute precision
    without timezone information.
    """
    ssl_warnings(enabled=sslwarnings)
    start = datetime.datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    end = datetime.datetime.strptime(end_date, "%Y-%m-%dT%H:%M")
    keystone = hm_keystone.client()
    nova = hm_nova.client()

    if tenant:
        tenants = {tenant: keystone.projects.get(tenant)}
        raw_usage = [nova.usage.get(tenant, start, end)]
    else:
        tenants = {x.id: x for x in keystone.projects.list()}
        raw_usage = nova.usage.list(start, end, detailed=True)

    usage = []
    for u in raw_usage:
        tenant_id = u.tenant_id
        tenant_name = tenants[tenant_id].name if tenant_id in tenants else None

        # The Nova API doesn't allow "show" on deleted instances, but
        # we can get the info using "list --deleted".  The problem is
        # figuring out how to avoid retrieving irrelevant instances,
        # and at the same time how to avoid too many requests.
        #
        # Attempt #1 - use the tenant_id and the instance's name to
        # focus queries.
        # Attempt #2 - as #1, but after N lookups by name for a tenant,
        # just fetch all of the deleted instances.
        cache = {}
        try:
            for iu in u.server_usages:
                name = iu['name']
                instance_id = iu['instance_id']
                instance = None
                if iu['state'] == 'terminated' or iu['state'] == 'deleted':
                    instance = _get_deleted_instance(
                        cache, nova, u.tenant_id, name, instance_id
                    )
                else:
                    try:
                        instance = nova.servers.get(instance_id).to_dict()
                    except Exception:
                        print(
                            f'Cannot find instance {instance_id} in {u.tenant_id}'
                        )
                if instance is None:
                    instance = {'OS-EXT-AZ:availability_zone': 'unknown'}

                usage.append(
                    [
                        tenant_id,
                        tenant_name,
                        instance_id,
                        name,
                        iu['state'],
                        iu['flavor'],
                        iu['hours'],
                        iu['vcpus'],
                        iu['memory_mb'],
                        iu['local_gb'],
                        instance['OS-EXT-AZ:availability_zone'],
                    ]
                )
        except Exception:
            traceback.print_exc(file=sys.stdout)

    headings = [
        "Tenant ID",
        "Tenant Name",
        "Instance id",
        "Instance name",
        "Instance state",
        "Flavour",
        "Instance hours",
        "vCPUs",
        "Memory (MB)",
        "Disk (GB)",
        "AZ",
    ]
    csv_output(headings, usage, filename=filename)


def _get_deleted_instance(cache, nova, tenant_id, name, instance_id):
    # Since we need to use 'list' to retrieve info about deleted instances,
    # we keep a cache of the instances we have previously retrieved.  For the
    # first few queries (< 4) we query by tenant_id & instance name.  After
    # that we do a query to fetch all deleted instances for the tenant ...
    if name in cache:  # Lookup instances for name
        instances = cache[name]
    elif len(cache) < 4:  # Caching for a name
        try:
            instances = nova.servers.list(
                detailed=True,
                search_opts={
                    'deleted': True,
                    'all_tenants': True,
                    'tenant_id': tenant_id,
                    'name': name,
                },
            )
            if len(instances) == 0:
                print(f"No deleted '{name}' instances in {tenant_id}")
        except Exception:
            print(f"Can't get deleted '{name}' instances in {tenant_id}")
            traceback.print_exc(file=sys.stdout)
            instances = []
        cache[name] = instances
    elif '*-*-ALL-*-*' in cache:  # Lookup the "all instances" name
        instances = cache['*-*-ALL-*-*']
    else:  # Cache "all instances"
        try:
            instances = nova.servers.list(
                detailed=True,
                search_opts={
                    'deleted': True,
                    'all_tenants': True,
                    'tenant_id': tenant_id,
                },
            )
            if len(instances) == 0:
                print(f"No deleted instances in {tenant_id}")
        except Exception:
            print(f"Can't get deleted instances in {tenant_id}")
            traceback.print_exc(file=sys.stdout)
            instances = []
        cache['*-*-ALL-*-*'] = instances
    # Lookup the specific instance in the cached list of deleted instances
    try:
        return filter(lambda i: i.id == instance_id, instances)[0].to_dict()
    except Exception:
        print(f'Cannot find deleted instance {instance_id} in {tenant_id}')
        return None


class NectarApiSession(requests.Session):
    """Class to encapsulate the rest api endpoint with a requests session."""

    def __init__(
        self,
        api_url=None,
        api_username=None,
        api_password=None,
        *args,
        **kwargs,
    ):
        username = os.environ.get('NECTAR_ALLOCATIONS_USERNAME', api_username)
        password = os.environ.get('NECTAR_ALLOCATIONS_PASSWORD', api_password)
        self.api_url = os.environ.get('NECTAR_ALLOCATIONS_URL', api_url)
        assert username and password and self.api_url
        requests.Session.__init__(self, *args, **kwargs)
        self.auth = (username, password)

    def _api_get(self, rel_url, *args, **kwargs):
        return self.get(f"{self.api_url}{rel_url}", *args, **kwargs)

    def get_allocations(self):
        req = self._api_get('/rest_api/allocations')
        req.raise_for_status()
        return req.json()

    def get_quotas(self):
        req = self._api_get('/rest_api/quotas')
        req.raise_for_status()
        return req.json()


@task
@verbose
def get_general_allocations_information(filename=None, sslwarnings=False):
    """Get standard allocations information and global quotas for all projects."""
    ssl_warnings(enabled=sslwarnings)
    api_endpoint = NectarApiSession()
    allocations = api_endpoint.get_allocations()
    fields_to_report = [
        ("Project ID", lambda x: x['project_id']),
        ("Project Name", lambda x: x['project_name']),
        ("Project Description", lambda x: x['project_description']),
        (
            "Allocation Home",
            lambda x: x['allocation_home']
            if 'allocation_home' in x and x['allocation_home'] is not None
            else "",
        ),
        ("Status", lambda x: x['status']),
        ("Modified time", lambda x: x['modified_time']),
        ("Instances", lambda x: x['instance_quota']),
        ("vCPU quota", lambda x: x['core_quota']),
        ("RAM quota", lambda x: x['ram_quota']),
        ("FOR 1", lambda x: x['field_of_research_1']),
        ("FOR 1 weighting (%)", lambda x: x['for_percentage_1']),
        ("FOR 2", lambda x: x['field_of_research_2']),
        ("FOR 2 weighting (%)", lambda x: x['for_percentage_2']),
        ("FOR 3", lambda x: x['field_of_research_3']),
        ("FOR 3 weighting (%)", lambda x: x['for_percentage_3']),
        ("Start date", lambda x: x['start_date']),
        ("End date", lambda x: x['end_date']),
    ]

    csv_output(
        map(lambda x: x[0], fields_to_report),
        map(
            lambda alloc: map(lambda y: y[1](alloc), fields_to_report),
            allocations,
        ),
        filename=filename,
    )


@task
@verbose
def get_local_allocations_information(
    filename=None, availability_zone=None, sslwarnings=False
):
    """Get local quota information for all projects."""
    ssl_warnings(enabled=sslwarnings)
    api_endpoint = NectarApiSession()
    allocations = {x['id']: x for x in api_endpoint.get_allocations()}
    quotas = {}
    quota_fields = []
    for q in api_endpoint.get_quotas():
        if q['zone'] != availability_zone and availability_zone is not None:
            continue
        if q['allocation'] not in quotas:
            quotas[q['allocation']] = collections.defaultdict(int)
        # qf = "%(zone)s-%(resource)s (%(units)s)" % q
        qf = "{zone}-{resource}".format(**q)
        quotas[q['allocation']][qf] = "{quota}".format(**q)
        if qf not in quota_fields:
            quota_fields.append(qf)

    fields_to_report = ["Project ID", "Project Name"]
    fields_to_report.extend(quota_fields)

    data_to_report = []
    for a_id in quotas:
        alloc = allocations[a_id]
        row = [alloc['project_id'], alloc['project_name']]
        row.extend(map(lambda x: quotas[a_id][x], quota_fields))
        data_to_report.append(row)
    csv_output(fields_to_report, data_to_report, filename=filename)
