from fabric.api import puts
from fabric.api import quiet
from fabric.api import run as f_run
from fabric.api import task
from prettytable import PrettyTable

from hivemind.operations import run


def list_instances():
    """List virtual machines on a host."""
    output = run("virsh list")
    headers = None
    servers = []
    for line in output.split("\n"):
        if headers is None:
            headers = [ln.lower() for ln in line.split()]
            continue
        if line.startswith("-----"):
            continue
        row = dict(zip(headers, line.split()))
        with quiet():
            row["uuid"] = f_run("virsh domuuid %s" % row["id"])
            row["nova_id"] = int(row['name'].split('-')[1], 16)
        servers.append(row)
    return servers


@task
def list():
    """List virtual machines on a host."""
    servers = list_instances()
    table = PrettyTable(["ID", "UUID", "Name", "State"])
    for server in servers:
        table.add_row([server["id"],
                       server['uuid'],
                       server['name'],
                       server["state"]])
    puts("\n" + str(table) + "\n")
