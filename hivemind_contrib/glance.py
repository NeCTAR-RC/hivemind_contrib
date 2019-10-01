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
    if image.get('nectar_name') != name:
        return False

    thisbuild = image.get('nectar_build')
    if not thisbuild:
        return False
    if int(thisbuild) < int(build):
        return True
    return False


@task
@decorators.verbose
def promote(image_id, dry_run=True, project=None, contributed=False):

    gc = client()
    try:
        image = gc.images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")

    if contributed:
        archive_project = get_contributed_project(project)
        promote_contributed(gc, image, dry_run, project=archive_project)
    else:
        archive_project = get_archive_project(project)
        promote_official(gc, image, dry_run, project=archive_project)


def promote_contributed(gc, image, dry_run, project):
    if dry_run:
        print("Running in dry run mode")

        if project:
            print("Would change ownership of image {} ({}) to "
                  "project {} ({})".format(image.name, image.id,
                      project.name, project.id))
    else:
        if project:
            print("Changing ownership of image {} ({}) to "
                  "project {} ({})".format(image.name, image.id,
                      project.name, project.id))
            now = datetime.datetime.now()
            publish_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            expire = now + datetime.timedelta(days=180)
            expiry_date = expire.strftime("%Y-%m-%dT%H:%M:%SZ")
            gc.images.update(image.id, owner=project.id,
                             published_at=publish_date,
                             expires_at=expiry_date)

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


def promote_official(gc, image, dry_run, project):
    """If the supplied image has nectar_name and nectar_build metadata, set
    to public. If there is an image with matching nectar_name and lower
    nectar_build, move that image to the <NECTAR_ARCHIVES> project.
    If the contributed flag is set please specify the contributed project id.
    """
    if dry_run:
        print("Running in dry run mode")

    try:
        name = image.nectar_name
        build = (int(image.nectar_build))
    except AttributeError:
        error("nectar_name or nectar_build not found for image.")

    m_check = partial(match, name, build)
    matchingimages = filter(m_check,
                            gc.images.list(filters={'owner': image.owner}))

    for i in matchingimages:
        archive_official(gc, i, dry_run, project)

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

    gc = client()
    try:
        image = gc.images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")

    if contributed:
        archive_project = get_contributed_archive_project(project)
        archive_contributed(gc, image, dry_run, archive_project)
    else:
        archive_project = get_archive_project(project)
        archive_official(gc, image, dry_run, archive_project)


def archive_contributed(gc, image, dry_run, project):
    if dry_run:
        print("Running in dry run mode")
        print("Would archive image {} ({}) to project {} ({})"
              .format(image.name, image.id,
                      project.name, project.id))
    else:
        print("Archiving image {} ({}) to project {} ({})"
              .format(image.name, image.id, project.name, project.id))
        gc.images.update(image.id, owner=project.id, visibility='community')


def archive_official(gc, image, dry_run, project):
    """Archive image by moving it to the <NECTAR_ARCHIVES> project.
    If the contributed flag is set
    please specify the contributed archive project id.
    """
    name = image.name
    try:
        build = '[v%s]' % image.nectar_build
    except AttributeError:
        error("nectar_build not found for image.")

    # Add build number to name if it's not already there
    # E.g. NeCTAR Ubuntu 17.10 LTS (Artful) amd64 (v10)
    if build not in name:
        name = '%s %s' % (name, build)

    if dry_run:
        print("Running in dry run mode")
        print("Would archive image {} ({}) to project {} ({})"
              .format(name, image.id,
                      project.name, project.id))
        if 'murano_image_info' in image:
            print('Would remove murano image properties from {}'
                  .format(image.id))
    else:
        print("Archiving image {} ({}) to project {} ({})"
              .format(name, image.id, project.name, project.id))
        gc.images.update(image.id, name=name, owner=project.id,
                         visibility='community', os_hidden=True)

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
        last_boot = 'Never'
        if boot_count > 0:
            last_boot = image_instances[0].created_at
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

        num = len(instances) if instances else 0
        table.add_row([i.id, name, official, build,
                       num, boot_count, last_boot])

    print(table.get_string(sortby="Running", reversesort=True))


@task
def official_audit():
    """Print usage information about official images
    """
    data = {}
    gc = client()
    nc = nova.client()
    db = nova.db_connect()

    images = []

    # NeCTAR-Images, NeCTAR-Images-Archive
    official_projects = ['28eadf5ad64b42a4929b2fb7df99275c',
                         'c9217cb583f24c7f96567a4d6530e405']

    for project in official_projects:
        images += list(gc.images.list(filters={'owner': project}))

    table = PrettyTable(["Name", "Running", "Boots"])

    table.align = 'l'
    table.align['Running'] = 'r'
    table.align['Boots'] = 'r'

    for i in images:
        sql = select([nova.instances_table])
        where = [nova.instances_table.c.image_ref.like(i.id)]
        sql = sql.where(*where).order_by(desc('created_at'))
        image_instances = db.execute(sql).fetchall()
        boot_count = len(image_instances)
        instances = nova.all_servers(nc, image=i['id'])

        if i.owner in official_projects or not i.owner:
            if i.name in data:
                data[i.name]['running'] += len(instances)
                data[i.name]['boots'] += boot_count
            else:
                data[i.name] = {'running': len(instances),
                                'boots': boot_count}

    for d in data.iteritems():
        table.add_row([d[0], d[1]['running'], d[1]['boots']])

    print(table.get_string(sortby="Running", reversesort=True))


@task
def official_images():
    """Print usage information about official images
    """
    gc = client()
    filters = {
        'visibility': 'public',
        'owner': '28eadf5ad64b42a4929b2fb7df99275c',
    }
    images = gc.images.list(filters=filters)

    table = PrettyTable(["ID", "Name", "Build", "Date"])
    table.align = 'l'

    for i in images:
        table.add_row([i.id, i.name, i.nectar_build, i.created_at])

    print(table.get_string(sortby="Name"))
