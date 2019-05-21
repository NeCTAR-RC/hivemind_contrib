from __future__ import print_function

from fabric.api import task
from prettytable import PrettyTable
from sqlalchemy import create_engine
from sqlalchemy import MetaData
from sqlalchemy import Table

from sqlalchemy.sql import and_
from sqlalchemy.sql import select

metadata = MetaData()


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
def show(connection, instance_uuid, debug=False):
    """display all allocations in nova_api db for instance

    :param str connection: database connection uri
    :param str instance_uuid: instance uuid
    :param bool debug (False): set true to see sql calls
    """
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
        print("existing allocations")
        print_table(results)


@task
def clean(connection, instance_uuid, hypervisor, debug=False, dry_run=True):
    """clean up multiple allocations in nova_api db for instance

    :param str connection: database connection uri
    :param str instance_uuid: instance uuid
    :param str hypervisor: hypervisor running the instance
    :param bool debug (False): set true to see sql calls
    :param bool dry_run (True): set false to make changes
    """
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
        print("would delete allocation id's %s\n" % ids)
    else:
        print("really would delete id's: %s\n" % ids)
