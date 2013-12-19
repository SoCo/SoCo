""" py.test hooks """


def pytest_addoption(parser):
    """ Add the --ip commandline option """
    parser.addoption(
        '--ip',
        type=str,
        default=None,
        action='store',
        dest='IP',
        help='the IP address for the zone to be used for the integration tests'
        )
