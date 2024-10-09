from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fabric.api import task
from fabric.utils import error
from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import log
from hivemind_contrib import nova
from hivemind_contrib import security
from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import Template

from jinja2.exceptions import TemplateNotFound

from prettytable import PrettyTable

import collections
import datetime
import io
import logging
import os
import re
import shutil
import smtplib
import sys
import tempfile
import time
import yaml


@decorators.configurable('smtp')
@decorators.verbose
def get_smtp_config(smtp_server=None,
                    sender='NeCTAR Research Cloud <bounces@rc.nectar.org.au>'):
    """fetch smtp parameters from config file"""
    msg = '\n'.join([
        'No smtp server parameter in either command options'
        + ' or your Hivemind config file.',
        '',
        'Use option --smtp-server SMTP_SERVER or',
        '',
        'Add the following config to your Hivemind configuration',
        'file (~/.hivemind/hivemind/config.ini):',
        '',
        '[cfg:hivemind_contrib.notification.smtp]',
        'smtp_server = <SMTP SERVER ADDRESS>',
    ])

    if smtp_server is None:
        error(msg)

    config = {'smtp_server': smtp_server, 'sender': sender}

    return config


class Mail_Sender(object):

    def __init__(self, config, debug=False):
        self.debug = debug
        self.smtp_server = config["smtp_server"]
        self.sender = config["sender"]
        self.smtp_obj = None
        self.smtp_msgs_per_conn = 100
        self.smtp_curr_msg_num = 1

    def send_email(self, recipient, subject, text, cc=None, html=True):
        msg = MIMEMultipart('alternative')
        if html:
            msg.attach(MIMEText(text, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(text, 'plain', 'utf-8'))

        msg['From'] = self.sender
        msg['To'] = recipient
        msg['Reply-to'] = 'support@nectar.org.au'
        msg['Subject'] = subject
        recipients = [recipient]
        if cc:
            msg['Cc'] = "; ".join(cc)
            recipients = [recipient] + cc

        self.smtp_curr_msg_num += 1
        if self.smtp_curr_msg_num > self.smtp_msgs_per_conn:
            print("Resetting SMTP connection.")
            try:
                self.smtp_obj.quit()
            except Exception as err:
                sys.stderr.write('Exception quit-ing SMTP:\n%s\n' % str(err))
            finally:
                self.smtp_obj = None

        if self.smtp_obj is None:
            self.smtp_curr_msg_num = 1
            self.smtp_obj = smtplib.SMTP(self.smtp_server)

        try:
            self.smtp_obj.sendmail(msg['From'], recipients, msg.as_string())
        except smtplib.SMTPRecipientsRefused as err:
            sys.stderr.write('SMTP Recipients Refused:\n')
            sys.stderr.write('%s\n' % str(err))
        except smtplib.SMTPException:
            # could maybe do some retry here
            sys.stderr.write('Error sending to %s ...\n' % recipient)
            raise
        sys.stdout.write('Successfully send mail to %s' % recipient)


class Generator(object):
    def __init__(self, template, subject):
        self.template_path, self.template_name = os.path.split(template)
        self.template_name = self.template_name.split('.')[0]
        self.subject_template = Template(subject)
        self.env = Environment(loader=FileSystemLoader(self.template_path),
                               trim_blocks=True)
        self.text_template = self.env.get_template('%s.tmpl' %
                                                   self.template_name)
        try:
            self.html_template = self.env.get_template('%s.html.tmpl' %
                                                       self.template_name)
        except TemplateNotFound:
            self.html_template = None

    def render_templates(self, instances, subject, start_ts, end_ts, tz, zone,
                         affected, nodes):
        duration = end_ts - start_ts if start_ts and end_ts else None
        days = duration.days if duration else None
        hours = duration.seconds // 3600 if duration else None

        text = self.text_template.render(
            {'instances': instances,
             'zone': zone,
             'start_ts': start_ts,
             'end_ts': end_ts,
             'days': days,
             'hours': hours,
             'tz': tz,
             'nodes': nodes,
             'affected': affected})
        if self.html_template:
            html = self.html_template.render(
                {'instances': instances,
                 'zone': zone,
                 'start_ts': start_ts,
                 'end_ts': end_ts,
                 'days': days,
                 'hours': hours,
                 'tz': tz,
                 'nodes': nodes,
                 'affected': affected})
        else:
            html = None

        return text, html

    def render_subject(self, instances):
        '''The default behavior is to perform template expansion on the
        subject parameter.
        '''
        return self.subject_template.render(
            {'instances': instances})


# populate_data() changes instances data structure from
# [INSTA, INSTB, INSTC, INSTD.....]
# to:
# { PROJECT1.ID:
#     "INSTANCE": [INSTA, INSTB]
#     "MANAGER": [PROJECT1.ROLE_ASSIGNMENT("MANAGER").email]
#   PROJECT2.ID:
#     "INSTANCE": [INSTC, INSTD]
#     "MANAGER": [PROJECT2.ROLE_ASSIGNMENT("MANAGER").email]
# }
def populate_data(instances):
    projects = _populate_project_dict(instances)
    return projects


def _populate_project_dict(instances):
    session = keystone.get_session()
    ksclient = keystone.client(session=session)
    project = collections.defaultdict(dict)
    for instance in instances:
        if instance['project_name'] in project.keys():
            project[instance['project_name']]['instances'].append(instance)
        else:
            cclist = []
            for role in ['TenantManager', 'Member']:
                members = keystone.list_members(instance['project'], role)
                if not members:
                    continue
                for uid in members.keys():
                    user = keystone.get_user(ksclient, uid, use_cache=True)
                    if getattr(user, 'enabled', None) and \
                       getattr(user, 'email', None):
                        cclist.append(user.email)
            # rule out the projects where has no valid recipients(tempest. etc)
            if cclist:
                project[instance['project_name']] = {'instances': [instance]}
                project[instance['project_name']].update(
                    {'recipients': cclist})

    return project


# modified from activestate recipes: http://code.activestate.com/recipes/
# 578094-recursively-print-nested-dictionaries/
# Pass 'tofile' the file handler to write, pass None to print in stdout
def print_dict(dictionary, tofile=None, ident='', braces=1):
    """Recursively prints nested dictionaries."""

    for key, value in dictionary.iteritems():
        if isinstance(value, dict):
            print("{}{}{}{}".format(ident, braces * "[",
                                    key, braces * "]"), file = tofile)
            print_dict(value, tofile, ident + '  ', braces + 1)
        else:
            table = _pretty_table_instances(value)
            if not isinstance(table, PrettyTable):
                print("{}{} = {}\n".format(ident, key, value), file = tofile)
            else:
                print("{}{} = \n{}\n".format(ident, key, table), file = tofile)


def _pretty_table_instances(instances):
    header = None
    for inst in instances:
        if not isinstance(inst, dict):
            return instances
        else:
            if not header:
                header = inst.keys()
                table = PrettyTable(header)
            table.add_row(inst.values())
    return table


def generate_logs(work_dir, data):
    with open(os.path.join(work_dir, "notify.log"), 'wb') as log:
        print_dict(data, log)


def normalize_filename(filename):
    illegal_chars = ['/']
    for c in illegal_chars:
        filename = re.sub(c, '_', filename)
    return filename


def generate_notification_mails(subject, template, data, work_dir,
                               start_time, end_time, timezone,
                               zone, affected, nodes):
    count = 0
    instances_list = []
    for proj, projvalues in data.items():
        if not projvalues['recipients']:
            continue
        inst = projvalues['instances']
        recipients = ','.join(projvalues['recipients'])
        generator = Generator(template, subject)
        msg, html = generator.render_templates(inst, subject, start_time,
                                               end_time, timezone, zone,
                                               affected, nodes)
        if not html:
            # convert to simple html, freshdesk supports html format only
            html = msg.replace("\n", "<br />\n")
            html = html.replace(r"\s", "&#160&#160&#160&#160")
        filename = normalize_filename("notification@" + proj)
        with io.open(os.path.join(work_dir, filename), 'w') as mail:
            count += 1
            content = {'Body': html, 'Sendto': recipients}
            yaml.dump(content, mail, default_flow_style=False)

        for ins in inst:
            instances_list.append(ins['id'])

    with open(os.path.join(work_dir, "instances.list"), 'w') as i:
        for ins in instances_list:
            i.write("%s\n" % ins)

    print("Totally %s mail(s) is generated" % count)


def is_email_address(mail):
    regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
    return True if regex.match(mail) else False


def get_email_address(mail):
    # user@domain.com@project, return (user@domain.com, project)
    regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
    match = regex.search(mail)
    if match:
        return [match.group(0), mail[match.end() + 1:]]
    else:
        return [None, None]


def get_instances_from_file(client, filename):
    with open(filename, 'r') as server_ids:
        for server_id in server_ids:
            yield client.servers.get(server_id.strip('\n'))


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def _validate_paramters(start_time, duration, instances_file, template):
    if not instances_file:
        if not start_time:
            print("No --start-time START_TIME: Please specify an outage\
                  start time. (e.g. '09:00 25-06-2015')")
            sys.exit(2)
        if not duration:
            print("No --duration DURATIOn: Please specify outage duratioan\
                  in hours.")
            sys.exit(2)

    if not os.path.exists(template):
        print("Template could not be found.")
        sys.exit(1)


def mailout(work_dir, data, subject, config):
    """Mailout the generated announcement emails

       :param str dir: Path to mail content
       :param str subject: Mail subject
       :param str config: mail sending configuration

    """
    print("You should run: hivemind notification.announcement_mailout "
          + "WITHOUT --no-dry-run first\n")
    print("It's also recommended to verify the email sending by: hivemind"
          + "notification.verify_mailout before proceeding with --no-dry-run")

    sender = Mail_Sender(config)
    mails = [f for f in os.listdir(work_dir) if os.path.isfile(
        os.path.join(work_dir, f)) and "notification@" in f]

    query = '\nMailout could send massive emails, please be cautious!!!!!\n'\
            'There are totally %s mails to be sent, still continue?'
    if not query_yes_no(query % len(mails), default='no'):
        sys.exit(1)

    print("Starting emails sending.....")
    for mail in mails:
        with io.open(os.path.join(work_dir, mail), 'rb') as f:
            content = yaml.load(f)
        addresses = content['Sendto'].split(',')
        toaddress = addresses.pop(0)

        sender.send_email(toaddress, subject, content['Body'], addresses)


def make_archive(work_dir):
    root = os.path.dirname(work_dir)
    base = os.path.basename(work_dir)
    shutil.make_archive(work_dir, "tar", root, base)
    shutil.rmtree(work_dir)


@task
@decorators.verbose
def announcement_mailout(template, zone=None, ip=None, nodes=None, image=None,
                         status="ALL", project=None, user=None,
                         subject="Important announcement concerning your "
                         "instance(s)", start_time=None, duration=0,
                         timezone="AEDT", smtp_server=None, sender=None,
                         instances_file=None, dry_run=True):
    """Generate mail announcements based on options.

       Some files will be generated and written into
       ~/.cache/hivemind-mailout/<time-stamp> in dry run mode,
       which are for operator check and no-dry-run use. They include: 1)
       notify.log: run log with all instances info and its email recipients;
       2) notification@<project-name>: rendered emails content and
       recipients; 3) instances.list: all impacted instances id

       :param str template: Template to use for the mailout (Mandatory)
       :param str zone: Availability zone affected by outage
       :param str ip: Only consider instances with specific ip addresses
       :param str nodes: Only target instances from the following Hosts/Nodes
       :param str image: Only consider instances with specific image
       :param str status: Only consider instances with status
       :param str subject: Custom email subject
       :param str start_time: Outage start time
       :param float duration: Duration of outage in hours
       :param str timezone: Timezone
       :param str instances_file: Only consider instances listed in file
       :param boolean dry_run: By default generate emails without sending out\
               use --no-dry-run to send all notifications
       :param str smtp_server: Specify the SMTP server
       :param str sender: Specify the mail sender
    """

    _validate_paramters(start_time, duration, instances_file, template)
    config = get_smtp_config(smtp_server, sender)

    start_time = datetime.datetime.strptime(start_time, '%H:%M %d-%m-%Y')\
                 if start_time else None
    end_time = start_time + datetime.timedelta(hours=int(duration))\
               if (start_time and duration) else None

    # find the impacted instances and construct data
    if not instances_file:
        instances = nova.list_instances(zone=zone, nodes=nodes, ip=ip,
                                        project=project, user=user,
                                        status=status, image=image)
    else:
        inst = get_instances_from_file(nova.client(), instances_file)
        instances = nova.extract_servers_info(inst)

    data = populate_data(instances)

    # write to logs and generate emails
    work_dir = os.path.join(os.path.expanduser('~/.cache/hivemind-mailout'),
                            datetime.datetime.now().strftime(
                                "%y-%m-%d_" + "%H:%M:%S"))
    print("Creating Outbox: " + work_dir)
    os.makedirs(work_dir)
    affected = len(data)
    if affected:
        generate_logs(work_dir, data)
        generate_notification_mails(subject, template, data, work_dir,
                                    start_time, end_time, timezone,
                                    zone, affected, nodes)
    else:
        print("No notification is needed, exit!")
        sys.exit(0)

    if dry_run:
        print("Finish writing email announcement in: " + work_dir)
        print("\nOnce you have checked the log file and generated emails")
        print("Use the command below to verify emails sending to test user:")
        print("\n hivemind notification.verify_mailout " + work_dir + " "
              + "SUBJECT" + " " + "[--mailto TEST_ADDRESS]" + " "
              + "[--smtp_server SMTP_SEVRVER]")
        print("\nThen rerun the command with --no-dry-run to mail ALL users")
    else:
        mailout(work_dir, data, subject, config)
        make_archive(work_dir)


@task
@decorators.verbose
def verify_mailout(dir, subject, sender=None, mailto=None, smtp_server=None):
    """Verify mail sending to specific test address.

       The command should be used after announcement_mailout command run.

       :param str dir: Path to mail content genearted by announcement_mailout
       :param str subject: Mail subject
       :param str sender: Specify the mail sender
       :param str mailto: Test mail address, xxxx@yyy.zzz
       :param str smtp_server: SMTP configuration
    """
    config = get_smtp_config(smtp_server, sender)
    mails = [f for f in os.listdir(dir) if os.path.isfile(
        os.path.join(dir, f)) and "notification@" in f]

    mail = mails[-1]
    sender = Mail_Sender(config)
    with open(os.path.join(dir, mail), 'rb') as f:
        content = yaml.load(f)
    if mailto:
        toaddress = mailto
        addresses = [mailto]
    else:
        mailto = content['Sendto']
        if not get_email_address(mailto):
            print("The mail address %s is not valid" % mailto)
            sys.exit(1)
        addresses = content['Sendto'].split(',')
        toaddress = addresses.pop(0)

    sender.send_email(toaddress, subject, content['Body'], addresses)


@task
@decorators.verbose
def freshdesk_mailout(template, zone=None, ip=None, nodes=None, image=None,
                      status="ALL", project=None, user=None,
                      subject="Important announcement concerning your "
                      "instance(s)", start_time=None, duration=None,
                      timezone="AEDT", instances_file=None,
                      dry_run=True, record_metadata=False,
                      metadata_field="notification:fd_ticket",
                      test_recipient=None):
    """Mailout announcements from freshdesk (Recommended).

       Freshdesk ticket per project will be created along with outbound email.
       Each mail will notify the first TenantManager and cc all other members.
       Once the customer responds to the mail, the reply will be appended to
       the ticket and status is changed to Open. Some files will be generated
       and written into ~/.cache/hivemind-mailout/freshdesk/<XXXX> in dry run
       mode, which are for operator check and no-dry-run use. They include: 1)
       notify.log: run log with all instances info and its email recipients;
       2) notification@<project-name>: rendered emails content and
       recipients; 3) instances.list: all impacted instances id

       :param str template: template path to use for the mailout
       :param str zone: Availability zone affected by outage
       :param str ip: Only consider instances with specific ip addresses
       :param str nodes: Only target instances from the following Hosts/Nodes
       :param str image: Only consider instances with specific image
       :param str status: Only consider instances with status
       :param str subject: Custom email subject
       :param str start_time: Outage start time
       :param float duration: duration of outage in hours
       :param str timezone: Timezone
       :param str instances_file: Only consider instances listed in file
       :param boolean dry_run: by default print info only, use --no-dry-run\
               for realsies. Log file notify_freshdesk.log will be generated\
               with ticket/emails info during the realsies run.
       :param boolean record_metadata: record the freshdesk ticket URL in\
               the nova instance metadata
       :param str metadata_field: set the name of the freshdesk ticket URL\
               metadata field in the nova instance."
    """
    fd_config = security.get_freshdesk_config()
    fd = security.get_freshdesk_client(fd_config['domain'],
                                       fd_config['api_key'])

    nc = nova.client()

    _validate_paramters(start_time, duration, instances_file, template)

    start_time = datetime.datetime.strptime(start_time, '%H:%M %d-%m-%Y')\
                 if start_time else None
    end_time = start_time + datetime.timedelta(hours=int(duration))\
               if (start_time and duration) else None

    work_dir = os.path.expanduser('~/.cache/hivemind-mailout/freshdesk/')

    if dry_run:
        # find the impacted instances and construct data
        if not instances_file:
            instances = nova.list_instances(zone=zone, nodes=nodes, ip=ip,
                                            project=project, user=user,
                                            status=status, image=image)
        else:
            inst = get_instances_from_file(nova.client(), instances_file)
            instances = nova.extract_servers_info(inst)
        # group by project
        data = populate_data(instances)
        if not data:
            print("No notification needed, exit!")
            sys.exit(0)

        affected = len(data)

        print("\n DRY RUN MODE - only generate notification emails: \n")
        # write to logs and generate emails
        if not os.path.isdir(work_dir):
            os.makedirs(work_dir)
        work_dir = tempfile.mkdtemp(dir=work_dir)
        print("Creating Outbox: " + work_dir)
        print('\nPlease export the environment variable for the no-dry-run: '
              'export %s=%s' % ('HIVEMIND_MAILOUT_FRESHDESK', work_dir))
        # render email content
        generate_logs(work_dir, data)
        generate_notification_mails(subject, template, data, work_dir,
                                    start_time, end_time, timezone,
                                    zone, affected, nodes)
    else:
        work_dir = os.environ.get('HIVEMIND_MAILOUT_FRESHDESK')
        if not work_dir or not os.path.isdir(work_dir):
            print('Workdir environment variable is not found!')
            print('Please run the command without --no-dry-run and '
                  'export environment variable as prompted!')
            sys.exit(0)

        email_files = [name for name in os.listdir(work_dir)
                       if os.path.isfile(os.path.join(work_dir, name))
                       and "notification@" in name]

        if test_recipient:
            print('You have specified the test_recipient option, '
                  'all the emails will be sent to %s' % test_recipient)

        query = '\nYou are running notification script in no-dry-run mode'\
                '\nIt will use previously generated emails under %s\n'\
                'Make sure the contents are all good before you do next step'\
                '\nOne outbounding email will create a separate ticket. '\
                'Be cautious since it could generate massive tickets!!!\n'\
                'There are %s tickets to be created, it takes roughly %s min '\
                'to finish all the creation, still continue?'
        if not query_yes_no(query % (work_dir, len(email_files),
                                     len(email_files) / 60 + 1), default='no'):
            sys.exit(1)

        log.logger(os.path.join(work_dir, 'notify_freshdesk.log'))

        subjectfd = "[Nectar Notice] " + subject
        for email_file in email_files:
            logging.info('Creating new Freshdesk ticket')
            with open(os.path.join(work_dir, email_file), 'rb') as f:
                email = yaml.load(f)
            if test_recipient:
                addresses = [test_recipient]
            else:
                addresses = email['Sendto'].split(',')
            toaddress = addresses[0]
            ccaddresses = addresses[1:]
            ticket = fd.tickets.create_outbound_email(
                description=email['Body'],
                subject=subjectfd,
                email=toaddress,
                cc_emails=ccaddresses,
                email_config_id=int(fd_config['email_config_id']),
                group_id=int(fd_config['group_id']),
                priority=2,
                status=5,  # set ticket initial status is closed
                tags=['notification'])
            ticket_id = ticket.id

            # Use friendly domain name if using prod
            if fd.domain == 'dhdnectar.freshdesk.com':
                domain = 'support.ehelp.edu.au'
            else:
                domain = fd.domain

            ticket_url = 'https://{}/helpdesk/tickets/{}'\
                         .format(domain, ticket_id)

            proj = email_file.split("@", 1)[1]
            logging.info('Ticket #{} has been created: <{}> for project <{}>'
                         .format(ticket_id, ticket_url, proj))
            logging.debug('Ticket #{} has email recipients: {}'
                         .format(ticket_id, addresses))

            if record_metadata:
                # Record the ticket URL in the server metadata
                for server in email[4]:
                    nc.servers.set_meta(server['id'],
                        {metadata_field: ticket_url})

            # delay for freshdesk api rate limit consideration
            time.sleep(1)

        # make achive the outbox folder
        logging.info('Make archive after the mailout for %s' % work_dir)
        make_archive(work_dir)
