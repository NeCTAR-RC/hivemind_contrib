from designateclient import client as designateclient
from fabric.api import task
from fabric.utils import error
from hivemind import decorators
from hivemind_contrib import keystone
from keystoneclient import exceptions as ks_exc


@decorators.configurable('nectar.openstack.client')
def client(version='2', sudo_project_id=None):
    sess = keystone.get_session()
    return designateclient.Client(
        version, session=sess, sudo_project_id=sudo_project_id
    )


@task
@decorators.verbose
def create_zone(zone_name, project_id_or_name, dry_run=True):
    """Create a designate zone for a user"""

    # Designate requires zone names to end with a dot.
    if not zone_name.endswith('.'):
        zone_name = f"{zone_name}."

    d_client = client()
    try:
        ks_client = keystone.client()
        project = keystone.get_project(ks_client, project_id_or_name)
    except ks_exc.NotFound:
        raise error(
            f"Project {project_id_or_name} not found. Check your settings."
        )
    except ks_exc.Forbidden:
        raise error(
            f"Permission denied getting project {project_id_or_name} details."
        )

    if dry_run:
        print(f"Would create designate zone {zone_name}")
        print(f"Would transfer zone {zone_name} to project {project.id}")
    else:
        d_client.session.sudo_project_id = None
        zone = d_client.zones.create(
            zone_name, email='support@rc.nectar.org.au'
        )
        print("Created new zone {}".format(zone['name']))
        print(
            "Transferring zone {} to project {}".format(
                zone['name'], project.id
            )
        )

        create_req = d_client.zone_transfers.create_request(
            zone_name, project.id
        )

        d_client.session.sudo_project_id = project.id
        accept_req = d_client.zone_transfers.accept_request(
            create_req['id'], create_req['key']
        )
        if accept_req['status'] == 'COMPLETE':
            print(
                "Zone {} transfer to project {} is complete".format(
                    zone['name'], project.id
                )
            )
        return zone
