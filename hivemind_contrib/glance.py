# hivemind_contrib/glance.py
import datetime
from fabric.api import task
from fabric.utils import error
from functools import partial
import glanceclient
from glanceclient import exc
from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova
from keystoneclient import exceptions as ks_exc
from prettytable import PrettyTable
from sqlalchemy import desc
from sqlalchemy.sql import select


def client():
    sess = keystone.get_session()
    return glanceclient.Client('2', session=sess)


def get_images_project(project_id_or_name, project_type):
    """fetch project id from config file"""
    if project_id_or_name is None:
        msg = " ".join(("No project set.", "Please set project in",
                        "[cfg:hivemind_contrib.glance.%s]" % project_type))
        error(msg)

    try:
        ks_client = keystone.client()
        project = keystone.get_project(ks_client, project_id_or_name)
    except ks_exc.NotFound:
        raise error("Project {} not found. Check your settings."
                    .format(project_id_or_name))
    except ks_exc.Forbidden:
        raise error("Permission denied. Check you're using admin credentials.")
    except Exception as e:
        raise error(e)

    return project


@decorators.configurable('contributedarchiveproject')
@decorators.verbose
def get_contributed_archive_project(project=None):
    return get_images_project(project, 'contributedarchiveproject')


@decorators.configurable('contributedproject')
@decorators.verbose
def get_contributed_project(project=None):
    return get_images_project(project, 'contributedproject')


@decorators.configurable('archiveproject')
@decorators.verbose
def get_archive_project(project=None):
    return get_images_project(project, 'archiveproject')


def match(name, build, image):
    """return true if image's name == name, and nectar_build < build"""
    try:
        if not image.get('nectar_name') == name:
            return False
    except KeyError:
        return False
    try:
        if not int(image.get('nectar_build')) < int(build):
            return False
    except KeyError:
        return False
    return True


@task
@decorators.verbose
def promote(image_id, dry_run=True, project=None, contributed=False):
    """If the supplied image has nectar_name and nectar_build metadata, set
    to public. If there is an image with matching nectar_name and lower
    nectar_build, move that image to the <NECTAR_ARCHIVES> project.
    If the contributed flag is set please specify the contributed project id.
    """
    if dry_run:
        print("Running in dry run mode")

    archive_project = None
    if project:
        if contributed:
            archive_project = get_contributed_project(project)
        else:
            archive_project = get_archive_project(project)

    gc = client()
    try:
        image = gc.images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")
    if not contributed:
        try:
            name = image.nectar_name
            build = (int(image.nectar_build))
        except AttributeError:
            error("nectar_name or nectar_build not found for image.")

        m_check = partial(match, name, build)
        matchingimages = filter(m_check,
                                gc.images.list(filters={'owner': image.owner}))
    else:
        matchingimages = [image]

    for i in matchingimages:
        if dry_run:
            if archive_project:
                print("Would change ownership of image {} ({}) to "
                      "project {} ({})".format(i.name, i.id,
                          archive_project.name, archive_project.id))
            if 'murano_image_info' in i:
                print('Would remove murano image properties from {}'
                      .format(i.id))
        else:
            if archive_project:
                print("Changing ownership of image {} ({}) to "
                      "project {} ({})".format(i.name, i.id,
                          archive_project.name, archive_project.id))
                now = datetime.datetime.now()
                publish_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                expire = now + datetime.timedelta(days=180)
                expiry_date = expire.strftime("%Y-%m-%dT%H:%M:%SZ")
                gc.images.update(i.id, owner=archive_project.id,
                                 published_at=publish_date,
                                 expires_at=expiry_date)
            if 'murano_image_info' in i:
                print('Removing murano image properties from {}'
                      .format(i.id))
                gc.images.update(i.id, remove_props=['murano_image_info'])

    if image.visibility == 'public':
        print("Image {} ({}) already set public"
              .format(image.name, image.id))
    else:
        if dry_run:
            print("Would set image {} ({}) to public"
                  .format(image.name, image.id))
        else:
            print("Setting image {} ({}) to public"
                  .format(image.name, image.id))
            gc.images.update(image.id, visibility='public')


@task
@decorators.verbose
def archive(image_id, dry_run=True, project=None, contributed=False):
    """Archive image by moving it to the <NECTAR_ARCHIVES> project.
    If the contributed flag is set
    please specify the contributed archive project id.
    """
    if dry_run:
        print("Running in dry run mode")

    archive_project = None
    if contributed:
        archive_project = get_contributed_archive_project(project)
    else:
        archive_project = get_archive_project(project)

    gc = client()
    try:
        image = gc.images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")

    if dry_run:
        if archive_project:
            print("Would archive image {} ({}) to project {} ({})"
                  .format(image.name, image.id,
                          archive_project.name, archive_project.id))
        if 'murano_image_info' in image:
            print('Would remove murano image properties from {}'
                  .format(image.id))
    else:
        if archive_project:
            print("Archiving image {} ({}) to project {} ({})"
                  .format(image.name, image.id,
                          archive_project.name, archive_project.id))
        gc.images.update(image.id, owner=archive_project.id)

        if 'murano_image_info' in image:
            print('Removing murano image properties from {}'.format(image.id))
            gc.images.update(image.id, remove_props=['murano_image_info'])


@task
def public_audit():
    """Print usage information about all public images
    """
    gc = client()
    nc = nova.client()
    db = nova.db_connect()

    # The visibility filter doesn't seem to work... so we filter them out again
    images = gc.images.list(visibility='public')
    public = [i for i in images if i['visibility'] == 'public']

    table = PrettyTable(["ID", "Name", "Official", "Build", "Running",
                         "Boots", "Last Boot"])

    table.align = 'l'
    table.align['Running'] = 'r'
    table.align['Boots'] = 'r'

    for i in public:
        sql = select([nova.instances_table])
        where = [nova.instances_table.c.image_ref.like(i.id)]
        sql = sql.where(*where).order_by(desc('created_at'))
        image_instances = db.execute(sql).fetchall()
        boot_count = len(image_instances)
        if boot_count > 0:
            last_boot = image_instances[0].created_at
        else:
            last_boot = 'Never'
        instances = nova.all_servers(nc, image=i['id'])

        # NeCTAR-Images, NeCTAR-Images-Archive
        official_projects = ['28eadf5ad64b42a4929b2fb7df99275c',
                             'c9217cb583f24c7f96567a4d6530e405']
        if i.owner in official_projects:
            official = 'Y'
        else:
            official = 'N'

        name = i.get('name', 'n/a')
        build = i.get('nectar_build', 'n/a')

        table.add_row([i.id, name, official, build,
                       len(instances), boot_count, last_boot])

    print(table.get_string(sortby="Running", reversesort=True))


@task
def official_audit():
    """Print usage information about official images
    """
    data = {}
    gc = client()
    nc = nova.client()
    db = nova.db_connect()

    # The visibility filter doesn't seem to work... so we filter them out again
    images = gc.images.list(visibility='public')
    public = [i for i in images if i['visibility'] == 'public']

    table = PrettyTable(["Name", "Running", "Boots"])

    table.align = 'l'
    table.align['Running'] = 'r'
    table.align['Boots'] = 'r'

    for i in public:
        sql = select([nova.instances_table])
        where = [nova.instances_table.c.image_ref.like(i.id)]
        sql = sql.where(*where).order_by(desc('created_at'))
        image_instances = db.execute(sql).fetchall()
        boot_count = len(image_instances)
        if boot_count > 0:
            last_boot = image_instances[0].created_at
        else:
            last_boot = 'Never'
        instances = nova.all_servers(nc, image=i['id'])

        # NeCTAR-Images, NeCTAR-Images-Archive
        official_projects = ['28eadf5ad64b42a4929b2fb7df99275c',
                             'c9217cb583f24c7f96567a4d6530e405']
        if i.owner in official_projects or i.owner == None:
            if i.name in data:
                data[i.name]['running'] += len(instances)
                data[i.name]['boots'] += boot_count
            else:
                data[i.name] = { 'running': len(instances),
                                 'boots': boot_count, }

    for d in data.iteritems():
        table.add_row([d[0], d[1]['running'], d[1]['boots']])

    print(table.get_string(sortby="Running", reversesort=True))
