from fabric.api import task
from hivemind.decorators import configurable

from .puppetdb import Puppetdb


@configurable('puppetdb')
def puppetdb(environment, host="puppet", port=8080, api_version=4):
    db = Puppetdb(hostname=host,
                  port=port,
                  api_version=api_version,
                  environment=environment)
    return db


def get_affected_hosts(classes, environment, certname_regex=None):
    queries = []
    classes = [cls.title() for cls in classes]
    classes_queries = [Puppetdb.equals('title', cls) for cls in classes]
    classes_query = Puppetdb.or_(classes_queries)
    queries.append(classes_query)
    type_query = Puppetdb.equals('type', 'Class')
    queries.append(type_query)
    if certname_regex:
        certname_query = Puppetdb.regex('certname', certname_regex)
        queries.append(certname_query)
    query = Puppetdb.and_(queries)

    db = puppetdb(host='mon', environment=environment)
    return db.get_nodes_for_resource(query)


@task
def affected_hosts(env, classes, subdomain=None):
    classes = classes.split(',')
    certname = None
    if subdomain is not None:
        certname = r'.*\\.%s\\.rc\\.nectar\\.org\\.au' % subdomain
    hosts = get_affected_hosts(classes, env, certname)
    for host in hosts:
        print host
