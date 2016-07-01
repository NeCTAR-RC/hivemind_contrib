from fabric.api import task
from fabric.utils import error

from novaclient import exceptions as n_exc

from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova
from hivemind_contrib.show import generate_instance_info
from hivemind_contrib.show import generate_instance_sg_rules_info

try:
    from freshdesk.v2.api import API
except:
    # OK missing for testing
    API = None


@decorators.configurable('freshdesk')
@decorators.verbose
def get_freshdesk_config(api_key=None,
                         domain='dhdnectar.freshdesk.com'):
    """fetch freshdesk API details from config file"""
    msg = '\n'.join([
        'No Freshdesk API key found in your Hivemind config file.',
        '',
        'To find your Freshdesk API key by following the guide here:',
        'https://support.freshdesk.com/support/solutions/'
        'articles/215517-how-to-find-your-api-key',
        '',
        'Then add the following config to your Hivemind configuration',
        'file (~/.hivemind/hivemind/config.ini):',
        '',
        '  [cfg:hivemind_contrib.security.freshdesk]',
        '  api_key = <your api key>',
    ])

    if api_key is None:
        error(msg)
    return (domain, api_key)


def get_freshdesk_client():
    domain, api_key = get_freshdesk_config()
    if not API:
        error("You will need to install python-freshdesk to use this function")
    return API(domain, api_key)


def get_ticket_recipients(instance):
    """Build a list of email addresses"""
    email_addresses = []

    kc = keystone.client()
    user = keystone.get_user(kc, instance.user_id)
    if user.email:
        email_addresses.append(user.email)

    # Add tenant members to ticket recipient list
    tenant = keystone.get_tenant(kc, instance.tenant_id)
    for user in tenant.list_users():
        roles = [r.name for r in user.list_roles(tenant)]
        if 'TenantManager' in roles:
            email_addresses.append(user.email)
    return email_addresses


@task
@decorators.verbose
def lock_instance(instance_id, dry_run=True):
    """pause and lock an instance"""
    if dry_run:
        print('Running in dry-run mode')

    fd = get_freshdesk_client()
    nc = nova.client()
    kc = keystone.client()
    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error('Instance {} not found'.format(instance_id))

    ticket_id = None
    ticket_url = instance.metadata.get('security_ticket')
    if ticket_url:
        print('Found existing ticket: {}'.format(ticket_url))
        ticket_id = int(ticket_url.split('/')[-1])

        if dry_run:
            print('Would set ticket #{} status to open/urgent'
                  .format(ticket_id))
        else:
            # Set ticket status=open, priority=urgent
            print('Setting ticket #{} status to open/urgent'.format(ticket_id))
            fd.tickets.update_ticket(ticket_id, status=2, priority=4)
    else:
        tenant = keystone.get_tenant(kc, instance.tenant_id)
        user = keystone.get_user(kc, instance.user_id)
        email_addresses = get_ticket_recipients(instance)

        # Create ticket if none exist, and add instance info
        subject = 'Security incident for instance {}'.format(instance_id)
        body = '<br />\n'.join([
            'Dear NeCTAR Research Cloud User, ',
            '',
            '',
            'We have reason to believe that cloud instance: '
            '<b>{} ({})</b>'.format(instance.name, instance.id),
            'in the project <b>{}</b>'.format(tenant.name),
            'created by <b>{}</b>'.format(user.email),
            'has been involved in a security incident.',
            '',
            'We have opened this helpdesk ticket to track the details and ',
            'the progress of the resolution of this issue.',
            '',
            'Please reply to this email if you have any questions or ',
            'concerns.',
            '',
            'Thanks, ',
            'NeCTAR Research Cloud Team'
        ])

        if dry_run:
            print('Would create ticket with details:')
            print('  To:      {}'.format(','.join(email_addresses)))
            print('  Subject: {}'.format(subject))

            print('Would add instance details to ticket:')
            print(generate_instance_info(instance_id))
            print(generate_instance_sg_rules_info(instance_id))
        else:
            print('Creating new Freshdesk ticket')
            ticket = fd.tickets.create_ticket(
                description=body,
                subject=subject, email='no-reply@rc.nectar.org.au',
                priority=4, cc_emails=email_addresses, tags=['security'])
            ticket_id = ticket.id
            ticket_url = 'https://{}/helpdesk/tickets/{}'\
                         .format(fd.domain, ticket_id)
            nc.servers.set_meta(instance_id, {'security_ticket': ticket_url})
            print('Ticket #{} has been created: {}'
                  .format(ticket_id, ticket_url))

            # Add a private note with instance details
            print('Adding instance information to ticket')
            instance_info = generate_instance_info(instance_id, style='html')
            sg_info = generate_instance_sg_rules_info(instance_id,
                                                      style='html')
            body = '<br/><br/>'.join([instance_info, sg_info])
            fd.comments.create_note(ticket_id, body)

    if dry_run:
        print('Would pause and lock instance {}'.format(instance_id))
        print('Would update ticket with action')
    else:
        # Pause and lock
        if instance.status == 'PAUSED':
            print('Instance already paused, skipping')
        else:
            print('Pausing instance {}'.format(instance_id))
            instance.pause()

        print('Locking instance {}'.format(instance_id))
        instance.lock()

        # Add reply to user
        print('Replying to ticket with action details')
        action = 'Instance <b>{} ({})</b> has been <b>paused and locked</b> '\
                 'pending further investigation'\
                 .format(instance.name, instance_id)
        fd.comments.create_reply(ticket_id, action)


@task
@decorators.verbose
def unlock_instance(instance_id, dry_run=True):
    """unlock an instance"""
    if dry_run:
        print('Running in dry-run mode')

    fd = get_freshdesk_client()
    nc = nova.client()
    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error('Instance {} not found'.format(instance_id))

    ticket_id = None
    ticket_url = instance.metadata.get('security_ticket')
    if ticket_url:
        print('Found ticket: {}'.format(ticket_url))
        ticket_id = int(ticket_url.split('/')[-1])
    else:
        if not dry_run:
            error('No ticket found in instance metadata!')

    if dry_run:
        print('Would unpause and unlock instance {}'.format(instance_id))
        print('Would reply to ticket')
        print('Would resolve ticket')
    else:
        if instance.status != 'PAUSED':
            print('Instance not paused')
        else:
            print('Unpausing instance {}'.format(instance_id))
            instance.unpause()

        print('Unlocking instance {}'.format(instance_id))
        instance.unlock()

        # Add reply to user
        print('Replying to ticket with action details')
        action = 'Instance <b>{} ({})</b> has been <b>unpaused and '\
                 'unlocked</b>'.format(instance.name, instance_id)
        fd.comments.create_reply(ticket_id, action)

        # Set ticket status=resolved
        print('Setting ticket #{} status to resolved'.format(ticket_id))
        fd.tickets.update_ticket(ticket_id, status=4)


@task
@decorators.verbose
def delete_instance(instance_id, dry_run=True):
    """delete an instance"""
    if dry_run:
        print('Running in dry-run mode')

    fd = get_freshdesk_client()
    nc = nova.client()
    try:
        instance = nc.servers.get(instance_id)
    except n_exc.NotFound:
        error('Instance {} not found'.format(instance_id))

    ticket_id = None
    ticket_url = instance.metadata.get('security_ticket')
    if ticket_url:
        print('Found ticket: {}'.format(ticket_url))
        ticket_id = int(ticket_url.split('/')[-1])
    else:
        if not dry_run:
            error('No ticket found in instance metadata!')

    # DELETE!!!
    if dry_run:
        print('Would delete instance {}'.format(instance_id))
        print('Would reply to ticket')
        print('Would resolve ticket')
    else:
        print('Deleting instance {})'.format(instance_id))
        instance.delete()

        # Add reply to user
        print('Updating ticket with action')
        action = 'Instance <b>{} ({})</b> has been <b>deleted.</b>'\
                 .format(instance.name, instance_id)
        fd.comments.create_reply(ticket_id, action)

        # Set ticket status=resolved
        print('Resolving ticket #{}'.format(ticket_id))
        fd.tickets.update_ticket(ticket_id, status=4)
