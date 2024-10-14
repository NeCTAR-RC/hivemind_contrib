from fabric.api import task
from hivemind import decorators
from hivemind_contrib import nova
from novaclient import exceptions as n_exc
from prettytable import PrettyTable
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import MetaData
from sqlalchemy import Table

from sqlalchemy.dialects import mysql

from sqlalchemy.sql import and_
from sqlalchemy.sql import select

metadata = MetaData()

CONNECTION = None
ENGINE = None


@decorators.configurable('connection')
def connect(uri=None):
    """get db connection string from config"""
    global CONNECTION
    global ENGINE

    if uri is None:
        print(
            "no connection info in hivemind config or command line",
            "in hivemind config.ini create an entry like:",
            "[cfg:hivemind_contrib.placement.connection]",
            "uri = mysql+pymysql://user:pass@host:port/database",
            sep="\n",
        )
    if ENGINE is None:
        ENGINE = create_engine(uri)
    if CONNECTION is None:
        CONNECTION = ENGINE.connect()
    return CONNECTION, ENGINE


def print_table(data):
    """Prints a table from sqlalchemy results"""
    cols = data[0].keys()
    pt = PrettyTable(cols)
    pt.align = 'l'
    for row in data:
        pt.add_row(row)
    print(pt.get_string())


@task
def show_allocation(instance_id, debug=False):
    """display allocations in nova_api db for instance

    :param str instance_id: instance uuid
    :param str connection: specify db connection string
    :param bool debug (False): show sql calls
    """
    db_conn, engine = connect()

    alloc_tb = Table(
        'allocations', metadata, autoload=True, autoload_with=engine
    )
    res_tb = Table(
        'resource_providers', metadata, autoload=True, autoload_with=engine
    )

    query = (
        select(
            [
                alloc_tb.c.id,
                alloc_tb.c.consumer_id,
                alloc_tb.c.resource_provider_id,
                res_tb.c.name,
            ]
        )
        .select_from(
            alloc_tb.join(
                res_tb, alloc_tb.c.resource_provider_id == res_tb.c.id
            )
        )
        .where(alloc_tb.c.consumer_id == instance_id)
    )

    results = db_conn.execute(query).fetchall()

    if not results:
        print(f"no allocation records found for instance {instance_id}\n")
    else:
        print_table(results)


@task
def clean_allocation(instance_id, hypervisor, debug=False, dry_run=True):
    """clean up multiple allocations in nova_api db for instance

    :param str instance_id: instance uuid
    :param str hypervisor: hypervisor running the instance
    :param str connection: specify db connection string
    :param bool debug (False): show sql calls
    :param bool dry_run (True): commit changes to the db
    """
    db_conn, engine = connect()

    alloc_tb = Table(
        'allocations', metadata, autoload=True, autoload_with=engine
    )
    res_tb = Table(
        'resource_providers', metadata, autoload=True, autoload_with=engine
    )

    query = (
        select(
            [
                alloc_tb.c.id,
                alloc_tb.c.consumer_id,
                alloc_tb.c.resource_provider_id,
                res_tb.c.name,
            ]
        )
        .select_from(
            alloc_tb.join(
                res_tb, alloc_tb.c.resource_provider_id == res_tb.c.id
            )
        )
        .where(
            and_(
                res_tb.c.name != hypervisor,
                alloc_tb.c.consumer_id == instance_id,
            )
        )
    )

    results = db_conn.execute(query).fetchall()
    if not results:
        print(f"multiple allocation records not found for {instance_id}\n")
        return

    # need to check here that instance actually lives on hypervisor
    check = (
        select(
            [
                alloc_tb.c.consumer_id,
                res_tb.c.name,
                alloc_tb.c.resource_provider_id,
            ]
        )
        .select_from(
            alloc_tb.join(
                res_tb, alloc_tb.c.resource_provider_id == res_tb.c.id
            )
        )
        .where(
            and_(
                res_tb.c.name == hypervisor,
                alloc_tb.c.consumer_id == instance_id,
            )
        )
    )
    check_result = db_conn.execute(check).fetchall()
    if not check_result:
        print(
            f"WARN: instance {instance_id} does not have an allocation on {hypervisor}\n"
        )
        return

    ids = [r[0] for r in results]
    stmt = alloc_tb.delete().where(alloc_tb.c.id.in_(ids))

    if dry_run:
        print("extra allocations found:")
        print_table(results)
        print('would execute statement:')
        print(
            stmt.compile(
                dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        print("run with --no-dry-run to commit changes to the db")
    else:
        print("deleting extra allocations:")
        print_table(results)
        db_conn.execute(stmt)
        print("remaining allocations:")
        show_allocation(instance_id)


def _get_dup_allocation_instances(debug=False):
    db_conn, engine = connect()

    alloc_tb = Table(
        'allocations', metadata, autoload=True, autoload_with=engine
    )

    query = (
        select([alloc_tb.c.consumer_id])
        .where(alloc_tb.c.resource_class_id == 0)
        .having(func.count(alloc_tb.c.consumer_id) > 1)
        .group_by(alloc_tb.c.consumer_id)
    )

    results = db_conn.execute(query).fetchall()
    return [id for (id,) in results]


@task
def show_duplicate_allocations():
    """get list of instance uuids with duplicate allocations

    :param str connection: specify db connection string
    """
    dups = _get_dup_allocation_instances(False)
    if not dups:
        print("no duplicate allocation records found")
        return

    pt = PrettyTable(['Instance ID'])
    for i in dups:
        pt.add_row([i])
    print(pt)


@task
def clean_duplicate_allocations(debug=False, dry_run=True):
    """clean allocations of instance uuids with duplicate allocations

    :param str connection: specify db connection string
    :param bool debug (False): show sql calls
    :param bool dry_run (True): commit changes to the db
    """
    nc = nova.client()
    dups = _get_dup_allocation_instances(debug=debug)
    if not dups:
        print("no duplicate allocation records found\n")
        exit(0)
    else:
        for instance_id in dups:
            try:
                server = nc.servers.get(instance_id)
            except n_exc.NotFound:
                print(f"{instance_id} not found on any hypervisor, deleting")
                _del_all_allocations_for_instance(instance_id, debug, dry_run)
                continue
            except Exception:
                print(f'error retrieving instance {instance_id} details')
                exit(1)

            hypervisor = getattr(
                server, 'OS-EXT-SRV-ATTR:hypervisor_hostname', None
            )
            if hypervisor is not None:
                clean_allocation(server.id, hypervisor, debug, dry_run)
            else:
                print(f'couldnt find hypervisor for instance {instance_id}')
                exit(1)


def _del_all_allocations_for_instance(id, debug, dry_run):
    db_conn, engine = connect()

    alloc_tb = Table(
        'allocations', metadata, autoload=True, autoload_with=engine
    )
    stmt = alloc_tb.delete().where(alloc_tb.c.consumer_id == id)

    if dry_run:
        print(f'DRY_RUN would delete all allocations for {id}')
        print(
            stmt.compile(
                dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
    else:
        db_conn.execute(stmt)
