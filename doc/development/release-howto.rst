Release Procedures
==================

This document describes the necessary steps for creating a new release of SoCo.


Preparations
------------

* Assign a version number to the release, according to `semantic versioning
  <http://semver.org/>`_. Tag names should be prefixed with ``v``.

* Create a GitHub issue for the new version (eg `Release 0.7 #108
  <https://github.com/SoCo/SoCo/issues/108>`_). This issue can be used
  to discuss included changes, the version number, etc.

* Create a milestone for the planned release (if it does not already exist).
  The milestone can be used to track issues relating to the release. All
  relevant issues should be assigned to the milestone.

* Create the release notes in ``release_notes.html``.


Create and Publish
------------------

* Verify that all tests pass.

* Update the version number in ``__init__.py`` (see
  `example <https://github.com/SoCo/SoCo/commit/d35171213eabbc4>`_).

* Tag the current commit, eg

.. code-block:: bash

    git tag -a v0.7 -m 'release version 0.7'

* Push the tag. This will create a new release on GitHub.

.. code-block:: bash

    git push --tags

* Update the `GitHub release <https://github.com/SoCo/SoCo/releases/new>`_
  using the release notes from the documentation. The release notes can be
  abbreviated if a link to the documentation is provided.

* Upload the release to PyPI.

.. code-block:: bash

    python setup.py sdist bdist_wheel upload

* Enable doc builds for the newly released version on `Read the Docs
  <https://readthedocs.org/dashboard/soco/versions/>`_.


Wrap-Up
-------

* Create the milestone for the next release (with the most likely version
  number) and close the milestone for the current release.

* Share the news!
