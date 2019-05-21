from __future__ import print_function

from fabric.api import task
from hivemind import decorators
from prettytable import PrettyTable
from sqlalchemy import create_engine
from sqlalchemy import MetaData
from sqlalchemy import Table

from sqlalchemy.dialects import mysql

from sqlalchemy.sql import and_
from sqlalchemy.sql import select

metadata = MetaData()


@decorators.configurable('database')
def get_connection(connection=None):
    """get db connection string from config"""
    if connection is None:
        print("no connection info in hivemind config or command line")
        exit(1)
    return connection


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
def show(instance_uuid, connection=None, debug=False):
    """display all allocations in nova_api db for instance

    :param str instance_uuid: instance uuid
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
                     alloc_tb.c.consumer_id == instance_uuid)

    results = db_conn.execute(query).fetchall()

    if not results:
        print("no allocation records found for instance %s\n" % instance_uuid)
    else:
        print_table(results)


@task
def clean(instance_uuid, hypervisor, connection=None,
          debug=False, dry_run=True):
    """clean up multiple allocations in nova_api db for instance

    :param str instance_uuid: instance uuid
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
                           alloc_tb.c.consumer_id == instance_uuid))

    results = db_conn.execute(query).fetchall()

    if not results:
        print("multiple allocation records not found for %s\n" % instance_uuid)
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
    else:
        print("deleting extra allocations:")
        print_table(results)
        stmt = alloc_tb.delete().where(alloc_tb.c.id.in_(ids))
        db_conn.execute(stmt)
        print("remaining allocations:")
        show(instance_uuid)
