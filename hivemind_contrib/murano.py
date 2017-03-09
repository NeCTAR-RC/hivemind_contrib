from fabric.api import task

import os_client_config


def murano_client(url=None, username=None, password=None, project=None):
    return os_client_config.make_client('application-catalog', auth_url=url,
                                        username=username, password=password,
                                        project_name=project)


def is_in_project(project, user):
    return any([u == user for u in project.list_users()])


@task
def private_package(package_id, dry_run=True):
    """Make a Murano package private """

    if dry_run:
        print("Running in dry-run mode")

    m = os_client_config.make_client('application-catalog')

    package = m.packages.get(package_id)
    project_id = package.owner_id

    ks_client = os_client_config.make_client('identity')
    project = ks_client.tenants.get(project_id)
    project_admin_role = ks_client.roles.find(name='Admin')
    admin_user = ks_client.users.get(ks_client.session.get_user_id())

    if not is_in_project(project, admin_user):
        print("Adding user to project %s (%s)" % (project.name, project.id))
        project.add_user(admin_user, project_admin_role)

    if package.is_public:
        if dry_run:
            print("Would remove public flag for package %s" % package_id)
        else:
            print("Removing public flag for package %s for %s" %
                  (package_id, project_id))
            m = os_client_config.make_client('application-catalog',
                                             project_name=project.name)
            m.packages.toggle_public(package_id)
    else:
        print("Package is not public")

    if is_in_project(project, admin_user):
        print("Removing user from project %s (%s)" % (project.name,
                                                      project.id))
        project.remove_user(admin_user, project_admin_role)
