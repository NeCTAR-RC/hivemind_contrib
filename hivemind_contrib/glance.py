# hivemind_contrib/glance.py

from fabric.api import task
from fabric.utils import error
from glanceclient import client as glance_client
from glanceclient import exc

import keystone  # hivemind_contrib keystone
from hivemind.decorators import verbose, configurable

from functools import partial


def get_glance_client(kc, api_version=1, endpoint=None):
    if endpoint is None:
        image_endpoint = kc.service_catalog.url_for(service_type='image')
        image_endpoint = image_endpoint.replace('v1', '')
    else:
        image_endpoint = endpoint
    gc = glance_client.Client(api_version, image_endpoint, token=kc.auth_token)
    return gc


@configurable('archivetenant')
@verbose
def changetenant(image, tenant=None):
    """move image to new_tenant"""
    msg = " ".join(("No archive tenant set.", "Please set tenant in",
                    "[cfg:hivemind_contrib.glance.archivetenant]"))
    if tenant is None:
        error(msg)
    image.update(owner=tenant)


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
@verbose
def promote(image):
    """If the supplied image has nectar_name and nectar_build metadata, set
    to public. If there is an instance with matching nectar_name and lower
    nectar_build, move that instance to the <NECTAR_ARCHIVES> tenant."""
    images = get_glance_client(keystone.client()).images
    try:
        image = images.get(image)
    except exc.HTTPNotFound:
        error("Instance ID not found.")
    try:
        name = image.properties['nectar_name']
        build = (int(image.properties['nectar_build']))
    except KeyError:
        error("nectar_name or nectar_build not found for image.")
    m_check = partial(match, name, build)
    matchingimages = filter(m_check, images.findall(owner=image.owner))
    for i in matchingimages:
        changetenant(i)
        print " ".join(("moved ", i.id, i.name, "build",
                        i.properties['nectar_build'], "to tenant", i.owner))
    image.update(is_public=True)
