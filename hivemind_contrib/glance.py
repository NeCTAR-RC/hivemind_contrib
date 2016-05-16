# hivemind_contrib/glance.py
from fabric.api import task
from fabric.utils import error
from functools import partial
from glanceclient import client as glance_client
from glanceclient import exc
from keystoneclient import exceptions as ks_exc
from prettytable import PrettyTable
from sqlalchemy import desc
from sqlalchemy.sql import select

from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova


def get_glance_client(kc, api_version=1, endpoint=None):
    if endpoint:
        image_endpoint = endpoint
    else:
        image_endpoint = kc.service_catalog.url_for(service_type='image')
    return glance_client.Client(api_version, image_endpoint,
                                token=kc.auth_token)


@decorators.configurable('archivetenant')
@decorators.verbose
def get_archive_tenant(tenant=None):
    """fetch tenant id from config file"""
    msg = " ".join(("No archive tenant set.", "Please set tenant in",
                    "[cfg:hivemind_contrib.glance.archivetenant]"))
    if tenant is None:
        error(msg)

    real_tenant = None
    try:
        ks_client = keystone.client()
        real_tenant = keystone.get_tenant(ks_client, tenant)
    except ks_exc.NotFound:
        raise error("Tenant {} not found. Check your settings."
                    .format(tenant))
    except ks_exc.Forbidden:
        raise error("Permission denied. Check you're using admin credentials.")
    except Exception as e:
        raise error(e)

    return real_tenant


@decorators.verbose
def change_tenant(image, tenant):
    """move image to new_tenant"""
    image.update(owner=tenant.id)


def match(name, build, image):
    """return true if image's name == name, and nectar_build < build"""
    try:
        if not image.properties['nectar_name'] == name:
            return False
    except KeyError:
        return False
    try:
        if not int(image.properties[u'nectar_build']) < int(build):
            return False
    except KeyError:
        return False
    return True


@task
@decorators.verbose
def promote(image_id, dry_run=True):
    """If the supplied image has nectar_name and nectar_build metadata, set
    to public. If there is an image with matching nectar_name and lower
    nectar_build, move that image to the <NECTAR_ARCHIVES> tenant."""
    if dry_run:
        print("Running in dry run mode")

    archive_tenant = get_archive_tenant()
    images = get_glance_client(keystone.client()).images
    try:
        image = images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")
    try:
        name = image.properties['nectar_name']
        build = (int(image.properties['nectar_build']))
    except KeyError:
        error("nectar_name or nectar_build not found for image.")

    m_check = partial(match, name, build)
    matchingimages = filter(m_check, images.findall(owner=image.owner))

    for i in matchingimages:
        if dry_run:
            print("Would archive image {} ({}) build {} to tenant {} ({})"
                  .format(i.name, i.id, i.properties['nectar_build'],
                          archive_tenant.name, archive_tenant.id))
        else:
            change_tenant(i, archive_tenant)
            print("Archiving image {} ({}) build {} to tenant {} ({})"
                  .format(i.name, i.id, i.properties['nectar_build'],
                          archive_tenant.name, archive_tenant.id))

    if image.is_public:
        print("Image {} ({}) already set public"
              .format(image.name, image.id))
    else:
        if dry_run:
            print("Would set image {} ({}) to public"
                  .format(image.name, image.id))
        else:
            print("Setting image {} ({}) to public")
            image.update(is_public=True)


@task
def public_audit():
    """Print usage information about all public images

    """
    gc = get_glance_client(keystone.client(), api_version=2)
    nc = nova.client()
    db = nova.db_connect()

    # The visibility filter doesn't seem to work... so we filter them out again
    images = gc.images.list(visibility='public')
    public = [i for i in images if i['visibility'] == 'public']

    table = PrettyTable(["ID", "Name", "Num running instances",
                         "Boot count", "Last Boot"])

    for i in public:
        sql = select([nova.instances_table])
        where = [nova.instances_table.c.image_ref.like(i['id'])]
        sql = sql.where(*where).order_by(desc('created_at'))
        image_instances = db.execute(sql).fetchall()
        boot_count = len(image_instances)
        if boot_count > 0:
            last_boot = image_instances[0].created_at
        else:
            last_boot = 'Never'
        instances = nova.all_servers(nc, image=i['id'])

        table.add_row([i['id'], i['name'],
                       len(instances), boot_count, last_boot])

    print(table.get_string(sortby="Num running instances", reversesort=True))
