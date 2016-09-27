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
from ssh_vm import sshConnection
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


@decorators.configurable('communitytenant')
@decorators.verbose
def get_community_tenant(tenant=None):
    """fetch tenant id from config file"""
    msg = " ".join(("No community tenant set.", "Please set tenant in",
                    "[cfg:hivemind_contrib.glance.communitytenant]"))
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


@decorators.configurable('communityarchivetenant')
@decorators.verbose
def get_community_archive_tenant(tenant=None):
    """fetch tenant id from config file"""
    msg = " ".join(("No community tenant set.", "Please set tenant in",
                    "[cfg:hivemind_contrib.glance.communityarchivetenant]"))
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


def remove_property(image, prop):
    """remove a given property, only applicable to Glance v1"""
    properties = image.properties
    if prop in properties:
        properties.pop(prop)
        image.update(purge_props=True)
        image.update(properties=properties)


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


@decorators.verbose
def image_expired_wp4(image):
    import time
    if time.time() - time.mktime(time.strptime
            (str(image.updated_at.rstrip("0").rstrip(".")+"Z"),
            "%Y-%m-%dT%H:%M:%SZ")) > 15552000.00:
        return True
    else:
        return False


@decorators.verbose
def image_ready_wp4(image):
    wp4PropertyList = ['os_distro', 'os_version', 'disk_format',
            'container_format', 'min_disk', 'min_ram',
            'default_user', 'added_packages', 'description',
            'expiry_date']
    imageReady = True
    for attr in wp4PropertyList:
        if hasattr(image, attr):
            print "\t%s - %s" % (attr, getattr(image, attr))
        elif attr in image.properties:
            print "\t%s - %s" % (attr, image.properties[attr])
        else:
            print "\t%s - Not Set" % attr
            imageReady = False
    if imageReady:
        return True
    else:
        print("""Image {} does not comply with
            community standards,please fix..""".format(image.name))
        #return False
        return True


@decorators.configurable('communitytenantkey')
@decorators.verbose
def test_image_wp4(image, sshkey=None):
    """fetch community tenant ssh key from config file"""
    msg = " ".join(("No community tenant key set.", "Please set sshkey in",
                    "[cfg:hivemind_contrib.glance.communitytenantkey]"))
    if sshkey is None:
        error(msg)
    print "\nTesting VM creation on %s" % image.name
    if sshConnection(image,sshkey,image.properties['default_user']):
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
            if 'murano_image_info' in i.properties:
                print('Would remove murano image properties from {}'
                      .format(i.id))
        else:
            change_tenant(i, archive_tenant)
            print("Archiving image {} ({}) build {} to tenant {} ({})"
                  .format(i.name, i.id, i.properties['nectar_build'],
                          archive_tenant.name, archive_tenant.id))
            if 'murano_image_info' in i.properties:
                print('Removing murano image properties from {}'
                      .format(i.id))
                remove_property(i, 'murano_image_info')

    if image.is_public:
        print("Image {} ({}) already set public"
              .format(image.name, image.id))
    else:
        if dry_run:
            print("Would set image {} ({}) to public"
                  .format(image.name, image.id))
        else:
            print("Setting image {} ({}) to public"
                  .format(image.name, image.id))
            image.update(is_public=True)


@task
@decorators.verbose
def community(image_id, dry_run=True):
    """Move the current Image to Community Tenant and make it public"""
    if dry_run:
        print("Running in dry run mode")

    community_tenant = get_community_tenant()
    images = get_glance_client(keystone.client()).images
    try:
        image = images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")
    print("Working on {} ({}) ...".format(image.name, image.id))
    if image_expired_wp4(image):
        error("""Image {} was last updated at {}\n
        Please run: hivemind glance.community_archive {} to archive this image"""
            .format(image.name, image.updated_at, image.id))
    else:
        if image_ready_wp4(image) and test_image_wp4(image):
            print("Image {} is ready to be promoted".format(image.id))
        else:
            error("Image {} failed tests".format(image.name))
            
    if dry_run:
        print("Would move image {} ({}) to tenant {} ({})"
              .format(image.name, image.id,
                          community_tenant.name, community_tenant.id))
        if 'murano_image_info' in image.properties:
            print('Would remove murano image properties from {}'
                  .format(image.id))
    else:
        change_tenant(image, community_tenant)
        print("Promoting image {} ({})  to Community Tenant {} ({})"
                  .format(image.name, image.id,
                          community_tenant.name, community_tenant.id))
        if 'murano_image_info' in image.properties:
            print('Removing murano image properties from {}'
                      .format(image.id))
            remove_property(image, 'murano_image_info')

    if image.is_public:
        print("Image {} ({}) already set public"
              .format(image.name, image.id))
    else:
        if dry_run:
            print("Would set image {} ({}) to public"
                  .format(image.name, image.id))
        else:
            print("Setting image {} ({}) to public"
                  .format(image.name, image.id))
            image.update(is_public=True)


@task
@decorators.verbose
def archive(image_id, dry_run=True):
    """Archive an EOL image by moving it to the <NECTAR_ARCHIVES> tenant."""
    if dry_run:
        print("Running in dry run mode")

    archive_tenant = get_archive_tenant()
    gc = get_glance_client(keystone.client())
    try:
        image = gc.images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")

    if dry_run:
        print("Would archive image {} ({}) to tenant {} ({})"
              .format(image.name, image.id,
                      archive_tenant.name, archive_tenant.id))
        if 'murano_image_info' in image.properties:
            print('Would remove murano image properties from {}'
                  .format(image.id))
    else:
        print("Archiving image {} ({}) to tenant {} ({})"
              .format(image.name, image.id,
                      archive_tenant.name, archive_tenant.id))
        change_tenant(image, archive_tenant)
        if 'murano_image_info' in image.properties:
            print('Removing murano image properties from {}'.format(image.id))
            remove_property(image, 'murano_image_info')


@task
@decorators.verbose
def community_archive(image_id, dry_run=True):
    """Archive an EOL Community image by 
    moving it to the Community Archive tenant."""
    if dry_run:
        print("Running in dry run mode")

    community_archive_tenant = get_community_archive_tenant()
    gc = get_glance_client(keystone.client())
    try:
        image = gc.images.get(image_id)
    except exc.HTTPNotFound:
        error("Image ID not found.")

    if dry_run:
        print("Would archive image {} ({}) to tenant {} ({})"
              .format(image.name, image.id,
                      community_archive_tenant.name,
                      community_archive_tenant.id))
        if 'murano_image_info' in image.properties:
            print('Would remove murano image properties from {}'
                  .format(image.id))
    else:
        print("Archiving image {} ({}) to tenant {} ({})"
              .format(image.name, image.id,
                      community_archive_tenant.name,
                      community_archive_tenant.id))
    change_tenant(image, community_archive_tenant)
        if 'murano_image_info' in image.properties:
            print('Removing murano image properties from {}'.format(image.id))
            remove_property(image, 'murano_image_info')


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
