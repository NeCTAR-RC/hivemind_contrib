import collections
from datetime import datetime
import logging
import socket
import time

from fabric.api import execute, run, settings, task
from hivemind.decorators import configurable
import pyrabbit.api as rabbit


LOG = logging.getLogger(__name__)


# This requires a config file in ~/.rabbitrc that looks something like:
#
# [environment_name]
# host =
# username =
# password =
# vhost =
#


@task
def monitor_queues(environment, vhost, fix=False):
    decorator = configurable('rabbitmq.management.%s' % environment)
    client = decorator(get_client)()

    stuck_queues = collections.defaultdict(lambda: 0)
    while True:
        do_check_queues(client, vhost, stuck_queues)
        fix_stuck_queues(client, stuck_queues, fix)
        time.sleep(1)


@task
def kill_process(host_, port):
    with settings(host_string='root@%s' % host_):
        run("kill `lsof -i :%s -Fp | sed 's/p//'`" % port)


def get_client(host, username, password):
    client = rabbit.Client(host=host,
                           user=username,
                           passwd=password)
    return client


def do_check_queues(client, vhost, stuck_queues):
    queues = client.get_queues(vhost=vhost)
    for queue in queues:
        name = queue['name']
        unacked = queue.get('messages_unacknowledged', 0)
        key = '%s:%s' % (vhost, name)
        if unacked > 0:
            stuck_queues[key] += 1
        elif key in stuck_queues:
            del stuck_queues[key]


def fix_stuck_queues(client, stuck_queues, fix, threshold=60):
    for vhost_queue, count in stuck_queues.items():
        if count < threshold:
            continue
        vhost, queue_name = vhost_queue.split(':')
        queue_info = client.get_queue(vhost, queue_name)
        unacked = queue_info.get('messages_unacknowledged', 0)
        now = str(datetime.today())
        print '%s: %s: %s unacknowledged messages.' % (
            now, queue_name, unacked)
        if fix and queue_name.startswith('reply'):
            fix_connections(client, queue_info)
        del stuck_queues[vhost_queue]


def fix_connections(client, queue_info):
    deliveries = queue_info['deliveries']
    for delivery in deliveries:
        channel = delivery['channel_details']
        host = channel['peer_host']
        port = channel['peer_port']
        hostname, _, _ = socket.gethostbyaddr(host)
        print 'Killing process at %s:%s' % (hostname, port)
        execute(kill_process, host, port)
