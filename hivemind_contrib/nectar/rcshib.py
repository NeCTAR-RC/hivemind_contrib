from urlparse import urlparse

from fabric.api import task, puts
from prettytable import PrettyTable
from sqlalchemy import create_engine
from sqlalchemy import (Table, Column, Integer, String,
                        DateTime, MetaData, Enum, PickleType)
from sqlalchemy.sql import not_, and_, select, func, or_

from hivemind.decorators import configurable

metadata = MetaData()
users = Table('user', metadata,
              Column('id', Integer, primary_key=True),
              Column('persistent_id', String(250), unique=True),
              Column('user_id', String(64)),
              Column('displayname', String(250)),
              Column('email', String(250)),
              Column('state', Enum("new", "registered", "created")),
              Column('terms', DateTime()),
              Column('shibboleth_attributes', PickleType))


@configurable('connection')
def connect(uri):
    engine = create_engine(uri)
    return engine.connect()


def idp_domain(persistent_id):
    """Convert a persistent id to a domain."""
    if persistent_id.startswith('http'):
        return urlparse(persistent_id).netloc
    if '!' in persistent_id:
        return persistent_id.split('!', 1)[0]
    return persistent_id


def print_users(user_list):
    table = PrettyTable(["ID", "Name", "Email", "User ID", 'IDP'])
    total = 0
    for user in user_list:
        total = total + 1
        table.add_row([user[users.c.id], user[users.c.displayname],
                       user[users.c.email], user[users.c.user_id],
                       idp_domain(user[users.c.persistent_id])])
    puts("\n" + str(table) + "\n")
    puts("Total: %s" % total)


@task
def search(display_name=None, email=None):
    """List users from RCShibboleth
    """
    db = connect()
    sql = select([users])
    where = []
    if display_name:
        where.append(users.c.displayname.like('%%%s%%' % display_name))
    if email:
        where.append(users.c.displayname.like('%%%s%%' % email))
    if len(where) > 1:
        sql = sql.where(and_(*where))
    elif where:
        sql = sql.where(*where)
    user_list = db.execute(sql)
    print_users(user_list)


@task
def find_duplicate(field=['email', 'displayname', 'user_id'], details=False):
    """Find duplicate users in RCShibboleth

       :param choices field: The field to choose
    """
    db = connect()
    fields = {
        'email': users.c.email,
        'displayname': users.c.displayname,
        'user_id': users.c.user_id
    }

    sql = select([users.c.user_id])
    sql = sql.group_by(users.c.user_id)
    sql = sql.having(func.count(users.c.user_id) > 1)
    result = db.execute(sql)
    ignored_ids = [row[0] for row in result]

    field = fields[field]
    sql = select([field, func.count(field)])
    sql = sql.group_by(field)
    sql = sql.having(func.count(field) > 1)

    result = db.execute(sql)

    user_list = []
    for row in result:
        filter = row[0]
        sql = select([users])
        sql = sql.where(and_(
            field == filter,
            or_(not_(users.c.user_id.in_(ignored_ids)),
                users.c.user_id == None)))
        sql = sql.where(field == filter)
        users1 = db.execute(sql)
        user_list.extend(users1)
    print_users(user_list)
