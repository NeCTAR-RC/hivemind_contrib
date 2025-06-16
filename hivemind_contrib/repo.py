import sys

from fabric import api as fapi
from prettytable import PrettyTable

from hivemind.decorators import verbose


def reprepro(command):
    with fapi.cd("/srv/nectar-ubuntu"):
        fapi.run(f"reprepro {command}")


@fapi.task
@verbose
@fapi.hosts("repo@debrepo.svc.artm.rc.nectar.org.au")
def list(distribution):
    """List all packages in a distribution."""
    reprepro(f"list {distribution}")


@fapi.task
@verbose
@fapi.hosts("repo@debrepo.svc.artm.rc.nectar.org.au")
def ls(package):
    """List the package version across all distributions."""
    reprepro(f"ls {package}")


@fapi.task
@verbose
@fapi.hosts("repo@debrepo.svc.artm.rc.nectar.org.au")
def compare_distribution(
    distribution1,
    distribution2=None,
    show_all=False,
    binary=False,
    promote=False,
):
    """Compare package versions across two distributions."""

    if promote and binary:
        print(
            "Error: --promote cannot be used with binary packages.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if distribution2 is None:
        distribution2 = distribution1 + '-testing'

    def parse_line(line):
        dist, name, version = line.split(" ")
        return (name, version)

    def get_packages(distribution):
        packages = fapi.run(
            "reprepro list {} | grep {} '|source: '".format(
                distribution, '-v' if binary else ''
            )
        )
        return dict(map(parse_line, packages.split('\r\n')))

    with fapi.cd("/srv/nectar-ubuntu"), fapi.hide("stdout"):
        packages1 = get_packages(distribution1)
        packages2 = get_packages(distribution2)

    pt = PrettyTable(['Package', distribution2, distribution1], caching=False)
    pt.align = 'l'
    for name in sorted(set(packages1.keys()) | set(packages2.keys())):
        version1 = packages1.get(name)
        version2 = packages2.get(name)
        promotable = version2 is not None
        different = version1 != version2
        if (different and promotable) or show_all:
            pt.add_row([name, version2 or "", version1 or ""])
    print(pt.get_string())

    if promote:
        print("")
        for name in sorted(packages2.keys()):
            version1 = packages1.get(name)
            version2 = packages2.get(name)
            promotable = version2 is not None and version1 != version2
            if promotable:
                print(f"Promoting {name}")
                print("  Old version: {}".format(version1 or "(not present)"))
                print(f"  New version: {version2}")
                _input = input("Proceed? (y/n/q) ")
                print("")
                if _input == 'y':
                    fapi.execute(
                        cp_package, name, distribution2, distribution1
                    )
                elif _input == 'q':
                    break
                else:
                    print(f"Skipping promotion of {name}")
                print("")


@fapi.task
@verbose
@fapi.hosts("repo@debrepo.svc.artm.rc.nectar.org.au")
def list_distributions():
    """List all the distributions."""
    with fapi.cd("/srv/nectar-ubuntu/dists"):
        fapi.run("ls")


@fapi.task
@verbose
@fapi.hosts("repo@debrepo.svc.artm.rc.nectar.org.au")
def cp_package(package, source, dest):
    """Copy a package from a source to a destination distribution."""
    with fapi.cd("/srv/nectar-ubuntu"), fapi.hide("stdout"):
        packages = fapi.run(
            f"reprepro listfilter {source} '$Source (=={package})' | "
            "awk '{print $2}' | sort | uniq"
        )
        if packages == '':
            print(f"Unable to find packages with source name '{package}'")
            print("Find source name from debian/control file in source")
            return

        fapi.run(
            "reprepro copy {} {} {}".format(
                dest, source, " ".join(packages.splitlines())
            )
        )


@fapi.task
@verbose
@fapi.hosts("repo@debrepo.svc.artm.rc.nectar.org.au")
def rm_packages(distribution, source_package):
    """Remove distribution packages that belong to the given source package."""
    reprepro(f"removesrc {distribution} {source_package}")
