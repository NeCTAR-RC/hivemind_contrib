import os
import time
import paramiko
import socket
import random
from fabric.utils import error
from hivemind import decorators
from hivemind_contrib import nova


@decorators.verbose
def sshConnection(image, sshKey, default_user):
    sshKeyName = sshKey.split('.')[0]
    nc = nova.client()
    if not nc.keypairs.findall(name=sshKeyName):
        print("\nNo SSH key with name %s found using ~/.ssh/id_rsa.pub" % sshKeyName)
        try:
            with open(os.path.expanduser('~/.ssh/id_rsa.pub')) as fpubkey:
                nc.keypairs.create(name=sshKeyName, public_key=fpubkey.read())
        except IOError as e:
            raise error(e)
    flavor = nc.flavors.find(name="m1.small")
    instance = nc.servers.create(name="wp4Test_"+ \
    str(random.randint(1, 1000)), image=image, flavor=flavor, key_name=sshKeyName)
    print("Building test instance {}...".format(instance.name))
    attempts=50
    attempt=1
    status = instance.status
    while attempt <= attempts:
        if status == 'ACTIVE': break
        time.sleep(5)
        instance = nc.servers.get(instance.id)
        status = instance.status
        attempt+=1
    if status != "ACTIVE":
        print("Connection timed out, please try again")
        instance.delete()
        return False
    print "\nChecking port 22..."
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    attempt = 1
    attempts = 20
    connected = False
    while attempt <= attempts:
        if not conn.connect_ex((instance.accessIPv4, 22)):
            connected = True
            break
        else:
            time.sleep(5)
        connected = False
    if not connected:
        print("Connection timed out...")
        instance.delete()
        return False
    sshConfig = paramiko.SSHConfig()
    try:
        sshConfig.parse(open(os.path.expanduser('~/.ssh/config')))
    except IOError:
        pass
    try:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(instance.accessIPv4, username=default_user,
            key_filename=os.path.expanduser('~/.ssh/')+sshKey, timeout=60)
        sftp = client.open_sftp()
        sftp.put('run_tests.sh', '/tmp/run_tests.sh')
        sftp.chmod('/tmp/run_tests.sh', 0551)
        sftp.put('assert.sh', '/tmp/assert.sh')
        sftp.chmod('/tmp/assert.sh', 0551)
        stdin, stdout, stderr = client.exec_command('/bin/bash /tmp/run_tests.sh')
        testFailed = False
        for line in stdout.readlines():
            if line.find("failed"):
                testFailed = True
            print line
    except paramiko.ssh_exception.AuthenticationException as e:
        raise error(e)
    except paramiko.ssh_exception.BadHostKeyException as e:
        raise error(e)
    finally:
        client.close()
        instance.delete()
        nc.keypairs.delete(key=sshKeyName)
    if testFailed:
        return False
    return True
