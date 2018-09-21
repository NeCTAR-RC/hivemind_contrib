from designateclient import client as designateclient
from fabric.api import task
from fabric.utils import error
from hivemind import decorators
from hivemind_contrib import keystone
from keystoneclient import exceptions as ks_exc


@decorators.configurable('nectar.openstack.client')
def client(version='2', sudo_project_id=None):
    sess = keystone.get_session()
    return designateclient.Client(version, session=sess,
                                  sudo_project_id=sudo_project_id)


@task
@decorators.verbose
def create_zone(zone_name, project_id_or_name, dry_run=True):
    """Create a designate zone for a user"""

    # Designate requires zone names to end with a dot.
    if not zone_name.endswith('.'):
        zone_name = "%s." % zone_name

    try:
        ks_client = keystone.client()
        project = keystone.get_project(ks_client, project_id_or_name)
    except ks_exc.NotFound:
        raise error("Project {} not found. Check your settings."
                    .format(project_id_or_name))
    except ks_exc.Forbidden:
        raise error("Permission denied getting project {} details."
                    .format(project_id_or_name))

    if dry_run:
        print("Would create designate zone {}".format(zone_name))
    else:
        d_client = client(sudo_project_id=project.id)
        zone = d_client.zones.create(zone_name,
                                     email='support@rc.nectar.org.au')
        print("Created new zone {}".format(zone['name']))
        return zone
