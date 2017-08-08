from fabric import api as fapi

from hivemind.decorators import verbose


def reprepro(command):
    with fapi.cd("/data/web/nectar-ubuntu"):
        fapi.run("reprepro {0}".format(command))


@fapi.task
@verbose
@fapi.hosts("repo@mirrors.melbourne.nectar.org.au")
def list(distribution):
    """List all packages in a distribution."""
    reprepro("list {0}".format(distribution))


@fapi.task
@verbose
@fapi.hosts("repo@mirrors.melbourne.nectar.org.au")
def ls(package):
    """List the package version across all distributions."""
    reprepro("ls {0}".format(package))


@fapi.task
@verbose
@fapi.hosts("repo@mirrors.melbourne.nectar.org.au")
def list_distributions():
    """List all the distributions."""
    with fapi.cd("/data/web/nectar-ubuntu/dists"):
        fapi.run("ls")


@fapi.task
@verbose
@fapi.hosts("repo@mirrors.melbourne.nectar.org.au")
def cp_package(package, source, dest):
    """Copy a package from a source to a destination distribution."""
    with fapi.cd("/data/web/nectar-ubuntu"), fapi.hide("stdout"):
        packages = fapi.run("reprepro listfilter %s '$Source (==%s)' | "
                            "awk '{print $2}' | sort | uniq" % (source,
                                                                package))
        if packages == '':
            print "Unable to find packages with source name '%s'" % package
            print "Find source name from debian/control file in source"
            return

        fapi.run("reprepro copy %s %s %s" %
            (dest, source, " ".join(packages.splitlines())))


@fapi.task
@verbose
@fapi.hosts("repo@mirrors.melbourne.nectar.org.au")
def rm_packages(distribution, source_package):
    """Remove distribution packages that belong to the given source package."""
    reprepro("removesrc {0} {1}".format(distribution, source_package))
