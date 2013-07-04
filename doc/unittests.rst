Unit tests
==========

The unit tests, written for the *SoCo* module, implements
elementary checks of whether the individual methods produce the
expected results. Such tests are especially useful during re-factoring
and to check that already implemented functionality continues to work
past updates to the Sonos units internal software.

Running the unit tests
----------------------

To run the unit tests enter the ``unittest`` folder in the source code
checkout and run the unit test execution script
``execute_unittests.py``. To run all the unit tests for the
*SoCo* module run:

.. code-block:: sh

    python execute_unittests.py --modules soco --ip 192.168.0.110

where the IP address should be replaced with the IP address of the
Sonos unit you want to use for the unit tests (NOTE! At present the
unit tests for the *SoCo* module requires your Sonos® unit to be playing
local network music library tracks from the queue and have at least
two such tracks in the queue). You can get a list of all the units in
your network and their IP addresses by running:

.. code-block:: sh

    python execute_unittests.py --list

To get the help for the unit test execution script which contains a
description of all the options run:

.. code-block:: sh

    python execute_unittests.py --help
