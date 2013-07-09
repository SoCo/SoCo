Unit tests
**********

The unit tests, written for the *SoCo* module, implements
elementary checks of whether the individual methods produce the
expected results. Such tests are especially useful during re-factoring
and to check that already implemented functionality continues to work
past updates to the Sonos units internal software.

Running the unit tests
======================

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

Unit test code structure and naming conventions
===============================================

The unit tests for the *SoCo* code should be organized according to
the following guidelines.

One unit test module per class under test
-----------------------------------------

Unit tests should be organized into modules, one module, i.e. one
file, for each class that should be tested. The module should be named
similarly to the class except replacing CamelCase with underscores and
followed by ``_unittest.py``.

Example: Unit tests for the class ``FooBar`` should be stored in
``foo_bar_unittests.py``.

One unit test class per method under test
-----------------------------------------

Inside the unit test modules the unit test should be organized into
one unit test case class per method under test. In order for the test
execution script to be able to calculate the test coverage, the test
classes should be named the same as the methods under test except that
the lower case underscores should be converted to CamelCase. If the
method is private, i.e. prefixed with 1 or 2 underscores, the test
case class name should be prefixed with the word ``Private``.

Examples:

==========================  =========================
Name of method under test   Test case class name
==========================  =========================
``get_current_track_info``  ``GetCurrentTrackInfo``
``__parse_error``           ``PrivateParseError``
``_my_hidden_method``       ``PrivateMyHiddenMethod``
==========================  =========================
