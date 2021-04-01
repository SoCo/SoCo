#! /usr/bin/env python


""" Dump all known UPnP commands """

import argparse
import re

import soco
import soco.services


def main():
    """ Run the main script """
    parser = argparse.ArgumentParser(
        prog='',
        description='Dump data about Sonos services'
    )
    parser.add_argument(
        '-d', '--device',
        default=None,
        help="The ip address of the device to query. "
             "If none is supplied, a random device will be used"
    )
    parser.add_argument(
        '-s', '--service',
        default=None,
        help="Dump data relating to services matching this regexp "
             "only, e.g. %(prog)s -s GroupRenderingControl"
    )

    args = parser.parse_args()

    # get a zone player - any one will do
    if args.device:
        device = soco.SoCo(args.device)
    else:
        device = soco.discovery.any_soco()
    print("Querying %s" % device.player_name)
    # loop over each of the available services
    # pylint: disable=no-member
    services = (srv(device) for srv in soco.services.Service.__subclasses__())

    for srv in services:
        if args.service is None or re.search(
                args.service, srv.service_type):
            print_details(srv)


def print_details(srv):
    """ Print the details of a service
    """
    name = srv.service_type
    box = "=" * 79
    print("{0}\n|{1:^77}|\n{0}\n".format(box, name))
    for action in srv.iter_actions():
        print(action.name)
        print("~" * len(action.name))
        print("\n  Input")
        for arg in action.in_args:
            print("    ", arg)
        print("\n  Output")
        for arg in action.out_args:
            print("    ", arg)

        print("\n\n")


if __name__ == '__main__':
    main()
