from __future__ import print_function
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from fabric.api import task
from hivemind import decorators
from hivemind_contrib import keystone
from hivemind_contrib import nova
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


class Mail_Sender(object):

    def __init__(self, config, debug=False):
        self.config = config
        self.debug = debug
        self.smtp_server = config["smtp_server"]
        self.smtp_obj = None
        self.smtp_msgs_per_conn = 100
        self.smtp_curr_msg_num = 1

    def send_email(self, recipient, subject, text):
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(text, 'plani', 'utf-8'))

        msg['From'] = 'NeCTAR Research Cloud <bounces@rc.nectar.org.au>'
        msg['To'] = recipient
        msg['Reply-to'] = 'support@nectar.org.au'
        msg['Subject'] = subject

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


def find_related_users(instances, roles):
    inst = collections.defaultdict(list)
    owner = collections.defaultdict(list)
    related_user = collections.defaultdict(dict)

    for instance in instances:
        if instance['project'] in inst.keys():
            inst[instance['project']].append(instance)
        else:
            inst[instance['project']] = [instance]

        if instance['email'] in owner.keys():
            owner[instance['email']].append(instance)
        else:
            owner[instance['email']] = [instance]

        if roles:
            for role in roles:
                member = keystone.list_members(instance['project'], role)
                # e.g. {u'd979ecba2b394312b334b5b7009587b4': {'project_name':
                # u'pt-498','name': u'x.y@z', 'roles': [u'Member']}}
                name = member.values()[0]['name']
                if name not in owner.keys():
                    if name not in related_user.keys():
                        related_user[name][role] = [instance]
                    elif role not in related_user[name].keys():
                        related_user[name][role] = [instance]
                    else:
                        related_user[name][role].append(instance)

    return inst, owner, related_user


def generate_log(work_dir, owners, related_users):
    # write the result log
    with open(os.path.join(work_dir, "impacted_owner.log"), "wb") as log:
        for owner, instances in owners.items():
            header = None
            for inst in instances:
                if not header:
                    header = inst.keys()
                    table = PrettyTable(header)
                table.add_row(inst.values())
            log.write("\n\nImpacted user is: %s \n\n" % owner)
            log.write(str(table))

    if related_users:
        with open(os.path.join(work_dir, "impacted_others.log"), 'wb') as log:
            header = ["Role", "Instances"]
            for user, user_inst in related_users.items():
                table = PrettyTable(header)
                for roles, instances in user_inst.items():
                    table.add_row([roles, instances])
                log.write("\n\nImpacted other user is: %s \n\n" % user)
                log.write(str(table))


def generate_notification_for_owner(subject, template, owners, work_dir,
                                    start_time, end_time, timezone,
                                    zone, affected, nodes):
    owner_recipients = 0
    for user, inst in owners.items():
        generator = Generator(template, subject)
        msg, html = generator.render_templates(inst, subject, start_time,
                                               end_time, timezone, zone,
                                               affected, nodes)
        with open(os.path.join(work_dir, user), 'wb') as mail:
            owner_recipients += 1
            mail.write(msg)

    print("Totally %s mail(s) is generated" % owner_recipients)


def generate_notification_for_others(subject, template, roles, others,
                                     work_dir, start_time, end_time,
                                     timezone, zone, affected, nodes):
    other_recipients = 0
    for user, role_inst in others.items():
        for role, inst in role_inst.items():
            if role in roles:
                subject = "[%s]" % role + subject
                generator = Generator(template, subject)
                msg, html = generator.render_templates(inst, subject,
                                                       start_time, end_time,
                                                       timezone, zone,
                                                       affected, nodes)
                dirname = os.path.join(work_dir, role)
                os.makedirs(dirname)
                with open(os.path.join(dirname, user), 'wb') as mail:
                    other_recipients += 1
                    mail.write(msg)
    print("Totally %s related user mail" % other_recipients)


def is_email_address(mail):
    regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
    return True if regex.match(mail) else False


def get_instances_from_file(client, filename):
    with open(filename, 'r') as server_ids:
        for server_id in server_ids:
            yield client.servers.get(server_id.strip('\n'))


@task
@decorators.verbose
def generate_announcement(template, zone=None, ip=None, nodes=None, image=None,
                          status="ACTIVE", project=None, user=None,
                          subject=None, start_time=None, duration=0,
                          timezone="AEDT", test_recipient=None, scope=None,
                          instances_file=None, content_file=None):
    """Generate mail announcements based on selective conditions

       :param str template: template to use for the mailout
       :param str zone: Availability zone affected by outage
       :param str ip: Only consider instances with specific ip addresses
       :param str nodes: Only target instances from the following Hosts/Nodes
       :param str image: Only consider instances with specific image
       :param str status: Only consider instances with status
       :param str subject: Custom email subject
       :param str start_time: Outage start time
       :param float duration: duration of outage in hours
       :param str timezone: Timezone
       :param str test_recipient: Only generate notification to test_recipient
       :param list scope: Specify the notified roles: Members, TenantManager
       :param str instances_file: Only consider instances listed in file
       :param str content_file: Use static content file as the notification
    """
    # parameter validation
    start_time = datetime.datetime.strptime(start_time, '%H:%M %d-%m-%Y')
    end_time = start_time + datetime.timedelta(hours=int(duration))\
               if start_time else None

    if not instances_file:
        if not start_time:
            print("""No -st START_TIME: Please specify an outage start time.
                        (e.g. '09:00 25-06-2015')""")
            sys.exit(2)
        if not end_time:
            print("No -d DURATION: Please specify outage duration in hours.")
            sys.exit(2)

    if not os.path.exists(template):
        print("Template could not be found.")
        sys.exit(1)
    template = os.path.split(template)[1].split('.')[0]

    # find the impacted instances and users
    if not instances_file:
        instances = nova.list_instances(zone=zone, nodes=nodes, ip=ip,
                                        project=project, user=user,
                                        status=status, image=image)
    else:
        inst = get_instances_from_file(nova.client(), instances_file)
        instances = map(nova.extract_server_info, inst)

    scope = scope.split(",") if scope else None
    instances, owners, related_users = find_related_users(instances, scope)
    work_dir = '/tmp/outbox/' + datetime.datetime.now().strftime("%y-%m-%d_" +
                                                                 "%H:%M:%S")
    print("Creating Outbox: " + work_dir)
    os.makedirs(work_dir)
    affected = len(owners)

    subject = "Concerining the " + subject if subject else template
    if affected:
        generate_log(work_dir, owners, related_users)

    generate_notification_for_owner(subject, template, owners, work_dir,
                                    start_time, end_time, timezone,
                                    zone, affected, nodes)
    if scope:
        generate_notification_for_others(subject, template, scope,
                                         related_users, work_dir,
                                         start_time, end_time, timezone,
                                         zone, affected, nodes)

    print("Finish writing email annoucement in: " + work_dir)
    print("\nOnce you have checked the log file and generated emails")
    print("Use the command below to verify emails sending to test user:")
    print("\n hivemind notification.verify_mailout " + work_dir + " " +
          subject + " " + "TEST_ADDRESS" + " " + "SMTP_SEVRVER")
    print("\nUse the command below to send emails sending to ALL users:")
    print("\n hivemind notification.mailout " + work_dir + " " +
          subject + " " + "SMTP_SERVER")


@task
@decorators.verbose
def mailout(dir, subject, smtp_server, recipient_role=None):
    """Mailout the generated annoucement emails

       :param str dir: Path to mail content
       :param str subject: Mail subject
       :param str smtp_server: SMTP configuration
       :param str recipient_role: Mail other related recipient,
          such as Members or TenantManager of specific projects

    """
    print("You should run: hivemind notification.generate_announcement first")

    config = {"smtp_server": smtp_server}
    sender = Mail_Sender(config)
    mails = [f for f in os.listdir(dir)
             if os.path.isfile(os.path.join(dir, f)) and is_email_address(f)]

    query = 'Mailout could send massive emails, please be cautious!!!!!\n'\
            'There are totally %s mails to be sent, still continue?'
    if not query_yes_no(query % len(mails), default='no'):
        sys.exit(1)

    for mail in mails:
        with open(os.path.join(dir, mail), 'rb') as f:
            text = f.read()
        sender.send_email(mail, subject, text)

    query = 'There are totally %s mails to be sent as receipent is [%s] '\
            'of the project containing impacted instances, still continue?'

    if recipient_role:
        recipient_role = recipient_role.split(',')
        for role in recipient_role:
            role_dir = os.path.join(dir, role)
            if not os.path.exists(role_dir):
                print("No role %s found" % role)
                sys.exit(1)
            others = [g for g in os.listdir(role_dir) if is_email_address(g)]
            if not others:
                print("No valid email found for role [%s]" % role)
                sys.exit(1)
            if not query_yes_no(query % (len(others), role), default='no'):
                sys.exit(1)
            for other in others:
                with open(os.path.join(role_dir, other), 'rb') as f:
                    text = f.read()
                subject = "[%s]" % role + subject
                sender.send_email(other, subject, text)


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


@task
@decorators.verbose
def verify_mailout(dir, subject, mailto, smtp_server):
    """Verify mail sending by sending any of the generated\
       mails to specific test address

       :param str dir: Path to mail content
       :param str subject: Mail subject
       :param str mailto: Test mail address, xxxx@yyy.zzz
       :param str smtp_server: SMTP configuration
    """
    if not is_email_address:
        print("The mail address %s is not valid" % mailto)
        sys.exit(1)

    config = {"smtp_server": smtp_server}
    mails = [f for f in os.listdir(dir)
             if os.path.isfile(os.path.join(dir, f)) and is_email_address(f)]

    test = mails[0]
    sender = Mail_Sender(config)
    with open(os.path.join(dir, test), 'rb') as f:
        text = f.read()

    sender.send_email(mailto, subject, text)
