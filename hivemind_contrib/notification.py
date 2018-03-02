from __future__ import print_function

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from fabric.api import task
from fabric.utils import error
from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova
from hivemind_contrib import security
from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import Template

from jinja2.exceptions import TemplateNotFound

from prettytable import PrettyTable

import collections
import datetime
import os
import re
import smtplib
import sys
import time


@decorators.configurable('smtp')
@decorators.verbose
def get_smtp_config(smtp_server=None):
    """fetch smtp parameters from config file"""
    msg = '\n'.join([
        'No smtp server parameter in either command options' +
        ' or your Hivemind config file.',
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

    config = {'smtp_server': smtp_server}

    return config


class Mail_Sender(object):

    def __init__(self, config, debug=False):
        self.debug = debug
        self.smtp_server = config["smtp_server"]
        self.smtp_obj = None
        self.smtp_msgs_per_conn = 100
        self.smtp_curr_msg_num = 1

    def send_email(self, recipient, subject, text, cc=None):
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(text, 'plani', 'utf-8'))

        msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
        msg['To'] = recipient
        msg['Reply-to'] = 'support@nectar.org.au'
        msg['Subject'] = subject
        if cc:
            msg['Cc'] = "; ".join(cc)

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
            self.smtp_obj.sendmail(msg['From'], [recipient], msg.as_string())
        except smtplib.SMTPRecipientsRefused as err:
            sys.stderr.write('SMTP Recipients Refused:\n')
            sys.stderr.write('%s\n' % str(err))
        except smtplib.SMTPException:
            # could maybe do some retry here
            sys.stderr.write('Error sending to %s ...\n' % recipient)
            raise
        sys.stdout.write('Successfully send mail to %s' % recipient)


class Generator(object):
    def __init__(self, name, subject):
        self.template_name = name
        self.subject_template = Template(subject)
        self.env = Environment(loader=FileSystemLoader('templates'))
        self.text_template = self.env.get_template('%s.tmpl' % name)
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
# { USER.EMAIL:[
#     PROJECT1.ID:
#       "INSTANCE": [INSTA, INSTB]
#       "MANAGER": [PROJECT1.ROLE_ASSIGNMENT("MANAGER").email]
#     PROJECT2.ID:
#       "INSTANCE": [INSTC, INSTD]
#       "MANAGER": [PROJECT2.ROLE_ASSIGNMENT("MANAGER").email]
# ]}
def populate_data(instances, roles):
    users = _populate_user_dict(instances)
    for email, instances in users.items():
        projects = _populate_project_dict(instances, roles)
        users[email] = projects
    return users


def _populate_user_dict(instances):
    user = collections.defaultdict(list)
    for instance in instances:
        if not is_email_address(instance['email']):
            continue
        if instance['email'] in user.keys():
            user[instance['email']].append(instance)
        else:
            user[instance['email']] = [instance]
    return user


def _populate_project_dict(instances, roles):
    project = collections.defaultdict(dict)
    for instance in instances:
        if instance['project_name'] in project.keys():
            project[instance['project_name']]['instances'].append(instance)
        else:
            project[instance['project_name']] = {'instances': [instance]}
            if roles:
                for role in roles:
                    members = keystone.list_members(instance['project_name'],
                                                    role)
                    if members:
                        members = map(lambda x: x['name'], members.values())
                        project[instance['project_name']].update(
                            {role: members})
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
                print("{}{} = {}".format(ident, key, table), file = tofile)
            else:
                print("{}{} = \n{}\n".format(ident, key, table), file = tofile)


def _pretty_table_instances(instances):
    header = None
    for inst in instances:
        if not isinstance(inst, dict):
            table = inst
        else:
            if not header:
                header = inst.keys()
                table = PrettyTable(header)
            table.add_row(inst.values())
    return table


def generate_logs(work_dir, data):
    with open(os.path.join(work_dir, "notify.log"), 'wb') as log:
        print_dict(data, log)


def generate_notification_mails(subject, template, data, work_dir,
                               start_time, end_time, timezone,
                               zone, affected, nodes):
    recipient = 0
    for user, uservalues in data.iteritems():
        for proj, projvalues in uservalues.items():
            inst = projvalues['instances']
            generator = Generator(template, subject)
            msg, html = generator.render_templates(inst, subject, start_time,
                                                   end_time, timezone, zone,
                                                   affected, nodes)
            filename = user + "@" + proj
            with open(os.path.join(work_dir, filename), 'wb') as mail:
                recipient += 1
                mail.write(msg)

    print("Totally %s mail(s) is generated" % recipient)


def render_notification(generator, data, subject, start_time, end_time,
                        timezone, zone, affected, nodes, cc):
    for user, uservalues in data.iteritems():
        for proj, projvalues in uservalues.items():
            inst = projvalues['instances']
            msg, html = generator.render_templates(inst, subject, start_time,
                                                   end_time, timezone, zone,
                                                   affected, nodes)
            cc_list = []
            if cc:
                for c in cc:
                    cc_list.extend(projvalues[c])
            if not html:
                # convert to simple html, freshdesk supports html format only
                html = msg.replace("\n", "<br />\n")
            yield user, proj, cc_list, html


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
        choice = raw_input().lower()
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


def mailout(work_dir, data, subject, config, cc=None):
    """Mailout the generated annoucement emails

       :param str dir: Path to mail content
       :param str subject: Mail subject
       :param str config: mail sending configuration
       :param str cc: cc Mail other related recipient,
          such as Members or TenantManager of specific projects

    """
    print("You should run: hivemind notification.announcement_mailout " +
          "WITHOUT --no-dry-run first\n")
    print("It's also recommended to verify the email sending by: hivemind" +
          "notification.verify_mailout before proceeding with --no-dry-run")

    sender = Mail_Sender(config)
    mails = [get_email_address(f) for f in os.listdir(work_dir)
             if os.path.isfile(os.path.join(work_dir, f)) and "@" in f]

    query = '\nMailout could send massive emails, please be cautious!!!!!\n'\
            'There are totally %s mails to be sent, still continue?'
    if not query_yes_no(query % len(mails), default='no'):
        sys.exit(1)

    print("Starting emails sending.....")
    for mail in mails:
        if is_email_address(mail[0]):
            with open(os.path.join(work_dir, '@'.join(mail)), 'rb') as f:
                text = f.read()

            cc_list = []
            if cc:
                for c in cc:
                    c_list = data[mail[0]][mail[1]].get(c)
                    if c_list:
                        cc_list.extend(c_list)

            sender.send_email(mail[0], subject, text, cc_list)


@task
@decorators.verbose
def announcement_mailout(template, zone=None, ip=None, nodes=None, image=None,
                         status="ACTIVE", project=None, user=None,
                         subject=None, start_time=None, duration=0,
                         timezone="AEDT", test_recipient=None, cc = None,
                         smtp_server=None, instances_file=None, dry_run=True):
    """Generate mail announcements based on selective conditions

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
       :param str test_recipient: Only generate notification to test_recipient
       :param list cc: Comma separated roles(e.g.TenantManager)\
               which will be cc-ed
       :param str instances_file: Only consider instances listed in file
       :param boolean dry_run: By default generate emails without sending out\
               use --no-dry-run to send all notifications
       :param str smtp_server: Specify the SMTP server
    """

    _validate_paramters(start_time, duration, instances_file, template)
    config = get_smtp_config(smtp_server)

    start_time = datetime.datetime.strptime(start_time, '%H:%M %d-%m-%Y')\
                 if start_time else None
    end_time = start_time + datetime.timedelta(hours=int(duration))\
               if (start_time and duration) else None

    template = os.path.split(template)[1].split('.')[0]
    # find the impacted instances and construct data
    if not instances_file:
        instances = nova.list_instances(zone=zone, nodes=nodes, ip=ip,
                                        project=project, user=user,
                                        status=status, image=image)
    else:
        inst = get_instances_from_file(nova.client(), instances_file)
        instances = map(nova.extract_server_info, inst)

    cc = cc.split(",") if cc else None
    data = populate_data(instances, cc)

    # write to logs and generate emails
    work_dir = '/tmp/outbox/' + datetime.datetime.now().strftime("%y-%m-%d_" +
                                                                 "%H:%M:%S")
    print("Creating Outbox: " + work_dir)
    os.makedirs(work_dir)
    affected = len(data)

    subject = "Concerning the " + subject if subject else template
    if affected:
        generate_logs(work_dir, data)
        generate_notification_mails(subject, template, data, work_dir,
                                    start_time, end_time, timezone,
                                    zone, affected, nodes)
    else:
        print("No notification is needed, exit!")
        sys.exit(0)

    if dry_run:
        print("Finish writing email annoucement in: " + work_dir)
        print("\nOnce you have checked the log file and generated emails")
        print("Use the command below to verify emails sending to test user:")
        print("\n hivemind notification.verify_mailout " + work_dir + " " +
              "SUBJECT" + " " + "[--mailto TEST_ADDRESS]" + " " +
              "[--smtp_server SMTP_SEVRVER]")
        print("\nThen rerun the command with --no-dry-run to mail ALL users")
    else:
        mailout(work_dir, data, subject, config, cc)


@task
@decorators.verbose
def verify_mailout(dir, subject, mailto=None, smtp_server=None):
    """Verify mail sending to specific test address

       :param str dir: Path to mail content genearted by announcement_mailout
       :param str subject: Mail subject
       :param str mailto: Test mail address, xxxx@yyy.zzz
       :param str smtp_server: SMTP configuration
    """
    config = get_smtp_config(smtp_server)
    mails = [get_email_address(f) for f in os.listdir(dir)
             if os.path.isfile(os.path.join(dir, f)) and "@" in f]

    mail = mails[-1]
    if not mailto:
        mailto = mail[0]
    if not get_email_address(mailto):
        print("The mail address %s is not valid" % mailto)
        sys.exit(1)

    sender = Mail_Sender(config)
    with open(os.path.join(dir, '@'.join(mail)), 'rb') as f:
        text = f.read()
    sender.send_email(mailto, subject, text, [mailto])


@task
@decorators.verbose
def freshdesk_mailout(template, zone=None, ip=None, nodes=None, image=None,
                      status="ACTIVE", project=None, user=None,
                      subject=None, start_time=None, duration=None,
                      timezone="AEDT", cc=None, instances_file=None,
                      dry_run=True):
    """Mailout announcements from freshdesk (Recommended). Freshdesk tickets
       will be created along with outbound emails sending. Once the customer
       responds to the mail, the reply will be appended to the ticket and
       Status is changed to Open.

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
       :param str cc: Whether to cc related roles, like TenantManager
       :param str instances_file: Only consider instances listed in file
       :param boolean dry_run: by default print info only, use --no-dry-run\
               for realsies
    """
    fd_config = security.get_freshdesk_config()
    fd = security.get_freshdesk_client(fd_config['domain'],
                                       fd_config['api_key'])

    _validate_paramters(start_time, duration, instances_file, template)

    start_time = datetime.datetime.strptime(start_time, '%H:%M %d-%m-%Y')\
                 if start_time else None
    end_time = start_time + datetime.timedelta(hours=int(duration))\
               if (start_time and duration) else None

    template = os.path.split(template)[1].split('.')[0]
    # find the impacted instances and construct data
    if not instances_file:
        instances = nova.list_instances(zone=zone, nodes=nodes, ip=ip,
                                        project=project, user=user,
                                        status=status, image=image)
    else:
        inst = get_instances_from_file(nova.client(), instances_file)
        instances = map(nova.extract_server_info, inst)

    cc = cc.split(",") if cc else None
    data = populate_data(instances, cc)

    if dry_run:
        print("\n DRY RUN MODE - PRINT RECIPIENTS ONLY: \n")
        print_dict(data)
        sys.exit(0)
    else:
        if not data:
            print("No notification needed, exit!")
            sys.exit(0)
        affected = sum(len(v) for v in data.itervalues())
        query = '\nOne outbounding email will create a separate ticket. '\
                'Be cautious since it could generate massive tickets!!!\n'\
                'There are %s tickets to be created, it takes roughly %s min '\
                'to finish all the creation, still continue?'
        if not query_yes_no(query % (affected, affected / 60 + 1),
                            default='no'):
            sys.exit(1)

        subject = "Concerning the " + subject if subject else template
        generator = Generator(template, subject)
        emails = render_notification(generator, data, subject, start_time,
                                     end_time, timezone, zone, affected,
                                     nodes, cc)
        for email in emails:
            subject = "[Nectar Notice] " + subject.upper() + "@" + email[1]
            print('\nCreating new Freshdesk ticket')
            ticket = fd.tickets.create_outbound_email(
                name=" ".join(email[0].split("@")[0].split(".")).upper(),
                description=email[3],
                subject=subject,
                email=email[0],
                cc_emails=email[2],
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
            print('Ticket #{} has been created: {}'
                  .format(ticket_id, ticket_url))
            # delay for freshdesk api rate limit consideration
            time.sleep(1)
