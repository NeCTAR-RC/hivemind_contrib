from fabric.api import task
from prettytable import PrettyTable

from sqlalchemy import Column
from sqlalchemy import create_engine
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table

from sqlalchemy.sql import and_
from sqlalchemy.sql import select
from sqlalchemy.sql import update

from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.dialects.mysql import TINYINT

from hivemind.decorators import configurable


# Status map
STATUS = {'N': 'New',
          'E': 'Submitted',
          'A': 'Approved',
          'R': 'Declined',
          'X': 'Update/extension requested',
          'J': 'Update/extension declined',
          'P': 'Provisioned',
          'L': 'Legacy submission',
          'M': 'Legacy approved',
          'O': 'Legacy rejected'}


metadata = MetaData()
allocations = Table('rcallocation_allocationrequest', metadata,
              Column('id', INTEGER(11), primary_key=True, autoincrement=True),
              Column('status', String(1)),
              Column('created_by', String(100)),
              Column('submit_date', Date()),
              Column('project_name', String(200)),
              Column('contact_email', String(75)),
              Column('start_date', Date()),
              Column('end_date', Date()),
              Column('primary_instance_type', String(1)),
              Column('cores', INTEGER(11)),
              Column('core_hours', INTEGER(11)),
              Column('instances', INTEGER(11)),
              Column('use_case', LONGTEXT),
              Column('usage_patterns', LONGTEXT),
              Column('geographic_requirements', LONGTEXT),
              Column('field_of_research_1', String(6), nullable=True),
              Column('for_percentage_1', INTEGER(11), nullable=True),
              Column('field_of_research_2', String(6), nullable=True),
              Column('for_percentage_2', INTEGER(11), nullable=True),
              Column('field_of_research_3', String(6), nullable=True),
              Column('for_percentage_3', INTEGER(11), nullable=True),
              Column('tenant_uuid', String(36), nullable=True),
              Column('instance_quota', INTEGER(11), nullable=True),
              Column('ram_quota', INTEGER(11), nullable=True),
              Column('core_quota', INTEGER(11), nullable=True),
              Column('tenant_name', String(64), nullable=True),
              Column('status_explanation', LONGTEXT, nullable=True),
              Column('volume_zone', String(64), nullable=True),
              Column('object_storage_zone', String(64), nullable=True),
              Column('approver_email', String(75), nullable=True),
              Column('modified_time', DateTime, nullable=True),
              Column('parent_request_id', INTEGER(11), nullable=True),
              Column('convert_trial_project', TINYINT(1), nullable=True),
              Column('estimated_project_duration', INTEGER(11), nullable=True),
              Column('allocation_home', String(128), nullable=True),
              Column('nectar_support', String(255), nullable=True),
              Column('ncris_support', String(255), nullable=True),
              Column('funding_national_percent', INTEGER(11), nullable=True),
              Column('funding_node', String(128), nullable=True))


@configurable('connection')
def connect(uri):
    engine = create_engine(uri)
    return engine.connect()


def print_allocations(allocation_list):
    table = PrettyTable(['ID', 'Date', 'Status', 'Name', 'Contact',
                         'Tenant Name', 'Tenant UUID'])
    table.align = 'l'
    for allocation in allocation_list:
        table.add_row([
            allocation[allocations.c.id],
            allocation[allocations.c.submit_date],
            STATUS[allocation[allocations.c.status]],
            allocation[allocations.c.project_name],
            allocation[allocations.c.contact_email],
            allocation[allocations.c.tenant_name],
            allocation[allocations.c.tenant_uuid]])
    print(table)


def print_allocation(allocation):
    print_allocations([allocation])


@task
def search(id=None, name=None, email=None):
    db = connect()
    sql = select([allocations])
    where = [allocations.c.parent_request_id == None]  # noqa
    if id:
        where.append(allocations.c.id == id)
    if name:
        where.append(allocations.c.project_name.like('%%%s%%' % name))
    if email:
        where.append(allocations.c.contact_email.like('%%%s%%' % email))

    if len(where) > 1:
        sql = sql.where(and_(*where))
    elif where:
        sql = sql.where(*where)
    allocation_list = db.execute(sql)
    print_allocations(allocation_list)


def get_allocation(allocation_id):
    db = connect()
    sql = (select([allocations])
           .where(allocations.c.id == allocation_id))
    result = db.execute(sql)

    if result.rowcount == 0:
        print('Allocation {} not found'.format(allocation_id))
        return

    return result.fetchone()


@task
def update_contact(allocation_id, new_email):
    allocation = get_allocation(allocation_id)
    print_allocation(allocation)

    if allocation[allocations.c.contact_email] == new_email:
        print('Account contact already set to {}'.format(new_email))
        return

    print('Updating contact email address to {}'.format(new_email))
    db = connect()
    sql = (update(allocations)
           .where(allocations.c.id == allocation_id)
           .values(contact_email=new_email))
    result = db.execute(sql)

    if result.rowcount == 0:
        print('Something went wrong.')
        return

    allocation = get_allocation(allocation_id)
    print_allocation(allocation)
