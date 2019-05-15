from urlparse import urlparse

from fabric.api import task
from fabric.utils import error
from prettytable import PrettyTable
from sqlalchemy import Column
from sqlalchemy import create_engine
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import PickleType
from sqlalchemy import String
from sqlalchemy import Table

from sqlalchemy.sql import and_
from sqlalchemy.sql import func
from sqlalchemy.sql import not_
from sqlalchemy.sql import or_
from sqlalchemy.sql import select
from sqlalchemy.sql import update

from hivemind.decorators import configurable

from hivemind_contrib import keystone
from hivemind_contrib import nova


metadata = MetaData()
users = Table('user', metadata,
              Column('id', Integer, primary_key=True),
              Column('persistent_id', String(250), unique=True),
              Column('user_id', String(64)),
              Column('displayname', String(250)),
              Column('email', String(250)),
              Column('state', Enum("new", "registered", "created")),
              Column('terms_accepted_at', DateTime()),
              Column('registered_at', DateTime()),
              Column('terms_version', String(64)),
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
    table = PrettyTable(["ID", "Name", "Email", "User ID", 'State', 'IdP'])
    table.align = 'l'
    total = 0
    for user in user_list:
        total = total + 1
        table.add_row([user[users.c.id], user[users.c.displayname],
                       user[users.c.email], user[users.c.user_id],
                       user[users.c.state],
                       idp_domain(user[users.c.persistent_id])])
    print(table)
    print("Total: %s" % total)


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
        where.append(users.c.email.like('%%%s%%' % email))
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
                users.c.user_id is None)))
        sql = sql.where(field == filter)
        users1 = db.execute(sql)
        user_list.extend(users1)
    print_users(user_list)


def keystone_ids_from_email(db, email):
    sql = select([users.c.user_id])
    sql = sql.where(users.c.email == email)
    result = db.execute(sql)
    results = list(result)
    return list(set(map(lambda r: r[users.c.user_id], results)))


@task
def link_account(existing_email, new_email):
    db = connect()
    ids = keystone_ids_from_email(db, existing_email)
    new_email_ids = keystone_ids_from_email(db, new_email)

    if len(ids) != 1:
        print('User has multiple accounts with email %s' % existing_email)
        return

    user_id = ids[0]
    orphan_user_id = new_email_ids[0]

    print('%s: %s' % (existing_email, user_id))
    print('%s: %s' % (new_email, orphan_user_id))

    if user_id == orphan_user_id:
        print('Those accounts are already linked')
        return

    client = keystone.client()
    user = client.users.get(orphan_user_id)

    project = client.projects.get(user.default_project_id)
    servers = nova.client().servers.list(search_opts={
        'all_tenants': True, 'project_id': project.id})

    if len(servers):
        print('Soon to be orphaned project has active instances.')
        print('Advise user to terminate them.')
        return

    print()
    print('Confirm that you want to:')
    print(' - Link %s to account %s' % (new_email, existing_email))
    print(' - Disable orphan Keystone project %s' % (project.name))
    print(' - Disable orphan Keystone user %s' % (user.name))
    print()

    response = raw_input('(yes/no): ')
    if response != 'yes':
        return

    print('Linking account.')
    sql = (update(users)
           .where(users.c.email == new_email)
           .values(user_id=user_id))
    result = db.execute(sql)

    if result.rowcount == 0:
        print('Something went wrong.')
        return

    print('Disabling orphaned Keystone project %s (%s).' % (
        project.name, project.id))
    client.projects.update(project.id, enabled=False)
    print('Disabling orphaned Keystone user %s (%s).' % (user.name, user.id))
    client.users.update(user.id, enabled=False, name="%s-disabled" % user.name)
    print('All done.')


@task
def link_duplicate(email, dry_run=True):
    """Link multiple accounts. Useful for IdP persistant token change.
    """
    def get_users(db, email):
        db = connect()
        sql = select([users])
        sql = sql.where(users.c.email == email)
        result = db.execute(sql)
        return list(result)

    def print_users(user_list):
        table = PrettyTable(['ID', 'Name', 'Email', 'User ID', 'State', 'IdP'])
        for user in results:
            table.add_row([user[users.c.id], user[users.c.displayname],
                           user[users.c.email], user[users.c.user_id],
                           user[users.c.state],
                           idp_domain(user[users.c.persistent_id])])
        print(str(table))

    if dry_run:
        print('Running in dry-run mode (--no-dry-run for realsies)')

    db = connect()
    results = get_users(db, email)

    user_id = None
    update_ids = []
    for r in results:
        if r[users.c.state] == 'created':
            user_id = r[users.c.user_id]
        else:
            if r[users.c.state] == 'registered':
                update_ids.append(r[users.c.id])

    if not user_id:
        error('Keystone user ID not found for %s' % email)
        return

    if not update_ids:
        error('No duplicate rcshibboleth accounts found')
        return

    sql = (update(users)
           .where(users.c.id.in_(update_ids))
           .values(user_id=user_id, state='created'))

    if dry_run:
        print('Would link accounts for %s to user ID %s' % (email, user_id))
    else:
        print('Linking accounts for %s to user ID: %s' % (email, user_id))

    print_users(results)

    if not dry_run:
        result = db.execute(sql)
        if result.rowcount > 0:
            print('Updated %d entries' % result.rowcount)
        else:
            error('No entries updated. Something went wrong.')

        results = get_users(db, email)
        print_users(results)
