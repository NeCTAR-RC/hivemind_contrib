from __future__ import print_function

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


@decorators.configurable('connection')
def get_connection(uri=None):
    """get db connection string from config"""
    if uri is None:
        print("no connection info in hivemind config or command line",
              "in hivemind config.ini create an entry like:",
              "[cfg:hivemind_contrib.placement.connection]",
              "uri = mysql+pymysql://user:pass@host:port/database",
              sep="\n")
        exit(1)
    return uri


def connect(uri, debug):
    engine = create_engine(uri, echo=debug)
    return engine


def print_table(data):
    cols = data[0].keys()
    pt = PrettyTable(cols)
    pt.align = 'l'
    for row in data:
        pt.add_row(row)
    print(pt.get_string())


@task
def show_allocation(instance_id, connection=None, debug=False):
    """display allocations in nova_api db for instance

    :param str instance_id: instance uuid
    :param str connection: specify db connection string
    :param bool debug (False): show sql calls
    """
    connection = get_connection(connection)
    engine = connect(connection, debug)
    db_conn = engine.connect()

    alloc_tb = Table('allocations', metadata,
                     autoload=True, autoload_with=engine)
    res_tb = Table('resource_providers', metadata,
                   autoload=True, autoload_with=engine)

    query = select(
        [alloc_tb.c.id,
         alloc_tb.c.consumer_id,
         alloc_tb.c.resource_provider_id,
         res_tb.c.name]).select_from(
             alloc_tb.join(
                 res_tb,
                 alloc_tb.c.resource_provider_id == res_tb.c.id)).where(
                     alloc_tb.c.consumer_id == instance_id)

    results = db_conn.execute(query).fetchall()

    if not results:
        print("no allocation records found for instance %s\n" % instance_id)
    else:
        print_table(results)


@task
def clean_allocation(instance_id, hypervisor, connection=None,
          debug=False, dry_run=True):
    """clean up multiple allocations in nova_api db for instance

    :param str instance_id: instance uuid
    :param str hypervisor: hypervisor running the instance
    :param str connection: specify db connection string
    :param bool debug (False): show sql calls
    :param bool dry_run (True): commit changes to the db
    """
    connection = get_connection(connection)
    engine = connect(connection, debug)
    db_conn = engine.connect()

    alloc_tb = Table('allocations', metadata,
                     autoload=True, autoload_with=engine)
    res_tb = Table('resource_providers', metadata,
                   autoload=True, autoload_with=engine)

    query = select(
        [alloc_tb.c.id,
         alloc_tb.c.consumer_id,
         alloc_tb.c.resource_provider_id,
          res_tb.c.name]).select_from(
              alloc_tb.join(
                  res_tb,
                  alloc_tb.c.resource_provider_id == res_tb.c.id)).where(
                      and_(res_tb.c.name != hypervisor,
                           alloc_tb.c.consumer_id == instance_id))

    results = db_conn.execute(query).fetchall()

    if not results:
        print("multiple allocation records not found for %s\n" % instance_id)
        return

    ids = [r[0] for r in results]
    if dry_run:
        print("extra allocations found:")
        print_table(results)
        stmt = alloc_tb.delete().where(alloc_tb.c.id.in_(ids))
        print('would execute statement:')
        print(str(stmt.compile(
              dialect=mysql.dialect(),
              compile_kwargs={"literal_binds": True})))
        print("run with --no-dry-run to commit changes to the db")
    else:
        print("deleting extra allocations:")
        print_table(results)
        stmt = alloc_tb.delete().where(alloc_tb.c.id.in_(ids))
        db_conn.execute(stmt)
        print("remaining allocations:")
        show_allocation(instance_id)


def _get_dup_allocation_instances(connection, debug=False):
    """get list of instance uuids with duplicate allocations

    :param str connection: specify db connection string
    :param bool debug (False): show sql calls
    """
    connection = get_connection(connection)
    engine = connect(connection, debug)
    db_conn = engine.connect()

    alloc_tb = Table('allocations', metadata,
                     autoload=True, autoload_with=engine)

    query = select([alloc_tb.c.consumer_id]).where(
        alloc_tb.c.resource_class_id == 0).having(
            func.count(alloc_tb.c.consumer_id) > 1).group_by(
                alloc_tb.c.consumer_id)

    results = db_conn.execute(query).fetchall()
    return results


@task
def show_duplicate_allocations(connection=None):
    dups = _get_dup_allocation_instances(connection, False)
    if not dups:
        print("no duplicate allocation records found")
    else:
        print_table(dups)


@task
def clean_duplicate_allocations(connection=None, debug=False, dry_run=True):
    nc = nova.client()
    dups = _get_dup_allocation_instances(connection, debug=debug)
    if not dups:
        print("no duplicate allocation records found\n")
        exit(0)
    else:
        for i in (dups):
            try:
                server = nc.servers.get(i[0])
            except n_exc.NotFound:
                print("{} not found on any hypervisor, deleting".format(i[0]))
                _del_all_allocations_for_instance(connection,
                                                  i[0], debug, dry_run)
                continue
            except Exception:
                print('error retrieving instance {} details'.format(i[0]))
                exit(1)

            hypervisor = getattr(server,
                                 'OS-EXT-SRV-ATTR:hypervisor_hostname', None)
            if hypervisor is not None:
                _del_dup_allocations_for_instance(connection, server.id,
                                                  hypervisor, dry_run)
            else:
                print('couldnt find hypervisor for instance {}'.format(i[0]))
                exit(1)


def _del_all_allocations_for_instance(connection, id, debug, dry_run):
    if dry_run:
        print('DRY_RUN would delete all allocations for {}'.format(id))
    else:
        connection = get_connection(connection)
        engine = connect(connection, debug)
        db_conn = engine.connect()

        alloc_tb = Table('allocations', metadata,
                         autoload=True, autoload_with=engine)
        stmt = alloc_tb.delete().where(alloc_tb.c.consumer_id == id)
        db_conn.execute(stmt)


def _del_dup_allocations_for_instance(connection, id, host, dry_run):
    if dry_run:
        print('DRY_RUN clean allocation {} on {})'.format(id, host))
    else:
        clean_allocation(id, host, connection, dry_run)
