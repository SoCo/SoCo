"""Module to test the data structure classes with pytest."""


import pytest

from soco import data_structures
from soco.exceptions import DIDLMetadataError
from soco.xml import XML


def assert_xml_equal(left, right, explain=None):
    """Helper function for comparing XML elements.

    Causes useful information to be output under pytest as to the differences
    between elements

    Args
         left (Element): an Elementtree.Element to compare
         right (Element): an Element to compare it with

    Raises
        AssertionError: if the Elements do not match
    """

    def _build_explanation(left, right, explain):
        if left.tag != right.tag:
            explain.append(
                "tag <{}> does not match tag <{}>".format(left.tag, right.tag)
            )
        for name, value in left.attrib.items():
            if right.get(name) != value:
                explain.append(
                    "%s attribute of element <%s> does not match: %s=%r, %s=%r"
                    % (name, left.tag, name, value, name, right.get(name))
                )
        for name in right.attrib:
            if name not in left.attrib:
                explain.append(
                    "right element <%s> has attribute %s but left does not"
                    % (left.tag, name)
                )
        if left.text != right.text:
            explain.append(
                "text for element <{}>: {!r} != {!r}".format(
                    left.tag, left.text, right.text
                )
            )
        if left.tail != right.tail:
            explain.append(
                "tail for element <{}>: {!r} != {!r}".format(
                    left.tag, left.text, right.text
                )
            )
        for i1, i2 in zip(left, right):
            _build_explanation(i1, i2, explain)
        return

    explain = []
    _build_explanation(left, right, explain)
    if explain != []:
        header = "Comparing XML elements {} and {}".format(left, right)
        assert False, header + "\n".join(explain)


class TestResource:
    """Testing the Resource class."""

    def test_create_didl_resource_with_no_params(self):
        with pytest.raises(TypeError):
            res = data_structures.DidlResource()

    def test_create_didl_resource(self):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx")
        assert res.uri == "a%20uri"
        assert res.protocol_info == "a:protocol:info:xx"

    def test_create_didl_resource_to_from_element(self, helpers):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx", bitrate=3)
        elt = res.to_element()
        assert helpers.compare_xml(
            elt,
            XML.fromstring(
                b'<res bitrate="3" ' b'protocolInfo="a:protocol:info:xx">a%20uri</res>'
            ),
        )
        assert data_structures.DidlResource.from_element(elt) == res

    def test_didl_resource_to_dict(self):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx")
        rez = res.to_dict()
        assert rez["uri"] == "a%20uri"
        assert rez["protocol_info"] == "a:protocol:info:xx"
        assert len(rez) == 12

    def test_didl_resource_to_dict_remove_nones(self):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx")
        rez = res.to_dict(remove_nones=True)
        assert rez["uri"] == "a%20uri"
        assert rez["protocol_info"] == "a:protocol:info:xx"
        assert len(rez) == 2

    def test_didl_resource_from_dict(self):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx")
        rez = data_structures.DidlResource.from_dict(res.to_dict())
        assert res == rez

    def test_didl_resource_from_dict_remove_nones(self):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx")
        rez = data_structures.DidlResource.from_dict(res.to_dict(remove_nones=True))
        assert res == rez

    def test_didl_resource_eq(self):
        res = data_structures.DidlResource("a%20uri", "a:protocol:info:xx")
        assert res != data_structures.DidlObject(
            title="a_title", parent_id="pid", item_id="iid"
        )
        assert res is not None
        assert res == res


class TestDidlObject:
    """Testing the DidlObject base class."""

    didl_xml = """
    <item xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
      xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
      id="iid" parentID="pid" restricted="true">
        <dc:title>the_title</dc:title>
        <upnp:class>object</upnp:class>
        <dc:creator>a_creator</dc:creator>
        <desc id="cdudn"
          nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">DUMMY</desc>
    </item>
    """

    def test_create_didl_object_with_no_params(self):
        with pytest.raises(TypeError):
            didl_object = data_structures.DidlObject()

    def test_create_didl_object_with_disallowed_params(self):
        with pytest.raises(ValueError) as excinfo:
            didl_object = data_structures.DidlObject(
                title="a_title", parent_id="pid", item_id="iid", bad_args="other"
            )
        assert "not allowed" in str(excinfo.value)

    def test_create_didl_object_with_good_params(self):
        didl_object = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a_creator",
            desc="dummy",
        )
        assert didl_object is not None
        assert didl_object.title == "a_title"
        assert didl_object.parent_id == "pid"
        assert didl_object.item_id == "iid"
        assert didl_object.creator == "a_creator"
        assert didl_object.resources == []
        assert didl_object.desc == "dummy"

    def test_didl_object_from_wrong_element(self):
        # Using the wrong element
        elt = XML.fromstring("""<res>URI</res>""")
        with pytest.raises(DIDLMetadataError) as excinfo:
            didl_object = data_structures.DidlObject.from_element(elt)
        assert "Wrong element. Expected <item> or <container>, "
        "got <res> for class object" in str(excinfo.value)

    def test_didl_object_from_element(self):
        elt = XML.fromstring(self.didl_xml)
        didl_object = data_structures.DidlObject.from_element(elt)
        assert didl_object.title == "the_title"
        assert didl_object.parent_id == "pid"
        assert didl_object.item_id == "iid"
        assert didl_object.creator == "a_creator"
        assert didl_object.desc == "DUMMY"
        assert didl_object.item_class == "object"

    def test_didl_object_from_element_unoff_subelement(self):
        """Test that for a DidlObject created from an element with an
        unofficial .# specified sub class, that the sub class is
        completely ignored

        """
        elt = XML.fromstring(self.didl_xml.replace("object", "object.#SubClass"))
        didl_object = data_structures.DidlObject.from_element(elt)
        assert didl_object.item_class == "object"

    def test_didl_object_from_wrong_class(self):
        # mismatched upnp class
        bad_elt1 = XML.fromstring(
            """<item xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
              xmlns:dc="http://purl.org/dc/elements/1.1/"
              xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
              id="iid" parentID="pid" restricted="true">
                 <dc:title>the_title</dc:title>
                 <upnp:class>object.item</upnp:class>
                 <dc:creator>a_creator</dc:creator>
                 <desc id="cdudn"
                   nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
                   RINCON_AssociatedZPUDN
                 </desc>
               </item>
        """
        )
        with pytest.raises(DIDLMetadataError) as excinfo:
            didl_object = data_structures.DidlObject.from_element(bad_elt1)
        assert ("UPnP class is incorrect. Expected 'object', got 'object.item'") in str(
            excinfo.value
        )

    def test_didl_object_from_dict(self):
        didl_object = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a_creator",
            desc="dummy",
        )
        the_dict = {
            "title": "a_title",
            "parent_id": "pid",
            "item_id": "iid",
            "creator": "a_creator",
            "restricted": True,
            "desc": "dummy",
        }
        assert data_structures.DidlObject.from_dict(the_dict) == didl_object
        # adding in an attibute not in _translation should make no difference
        the_dict["creator"] = "another_creator"
        assert data_structures.DidlObject.from_dict(the_dict) != didl_object
        # round trip
        assert data_structures.DidlObject.from_dict(the_dict).to_dict() == the_dict

    def test_didl_object_from_dict_resources(self):
        resources_list = [data_structures.DidlResource("a%20uri", "a:protocol:info:xx")]
        didl_object = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a_creator",
            desc="dummy",
            resources=resources_list,
        )
        the_dict = {
            "title": "a_title",
            "parent_id": "pid",
            "item_id": "iid",
            "creator": "a_creator",
            "restricted": True,
            "desc": "dummy",
            "resources": [resource.to_dict() for resource in resources_list],
        }
        assert data_structures.DidlObject.from_dict(the_dict) == didl_object

    def test_didl_object_from_dict_resources_remove_nones(self):
        resources_list = [data_structures.DidlResource("a%20uri", "a:protocol:info:xx")]
        didl_object = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a_creator",
            desc="dummy",
            resources=resources_list,
        )
        the_dict = {
            "title": "a_title",
            "parent_id": "pid",
            "item_id": "iid",
            "creator": "a_creator",
            "restricted": True,
            "desc": "dummy",
            "resources": [
                resource.to_dict(remove_nones=True) for resource in resources_list
            ],
        }
        assert data_structures.DidlObject.from_dict(the_dict) == didl_object

    def test_didl_comparisons(self):
        didl_object_1 = data_structures.DidlObject(
            title="a_title", parent_id="pid", item_id="iid", creator="a_creator"
        )
        didl_object_2 = data_structures.DidlObject(
            title="a_title", parent_id="pid", item_id="iid", creator="a_creator"
        )
        # should be not the same, but equal!
        assert didl_object_1 is not didl_object_2
        assert didl_object_1 == didl_object_2
        didl_object_3 = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a__different_creator",
        )
        assert didl_object_3 != didl_object_1

    def test_didl_object_to_dict(self):
        didl_object = data_structures.DidlObject(
            title="a_title", parent_id="pid", item_id="iid", creator="a_creator"
        )
        the_dict = {
            "title": "a_title",
            "parent_id": "pid",
            "item_id": "iid",
            "creator": "a_creator",
            "restricted": True,
            "desc": "RINCON_AssociatedZPUDN",
        }
        assert didl_object.to_dict() == the_dict
        # adding in an attibute not in _translation should make no difference
        didl_object.other = "other"
        assert didl_object.to_dict() == the_dict
        # but changing on the other should
        didl_object.creator = "another"
        assert didl_object.to_dict() != the_dict

    def test_didl_object_to_dict_resources(self):
        resources_list = [data_structures.DidlResource("a%20uri", "a:protocol:info:xx")]
        didl_object = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a_creator",
            resources=resources_list,
        )
        the_dict = {
            "title": "a_title",
            "parent_id": "pid",
            "item_id": "iid",
            "creator": "a_creator",
            "restricted": True,
            "desc": "RINCON_AssociatedZPUDN",
            "resources": [resource.to_dict() for resource in resources_list],
        }
        assert didl_object.to_dict() == the_dict

    def test_didl_object_to_dict_resources_remove_nones(self):
        resources_list = [data_structures.DidlResource("a%20uri", "a:protocol:info:xx")]
        didl_object = data_structures.DidlObject(
            title="a_title",
            parent_id="pid",
            item_id="iid",
            creator="a_creator",
            resources=resources_list,
        )
        the_dict = {
            "title": "a_title",
            "parent_id": "pid",
            "item_id": "iid",
            "creator": "a_creator",
            "restricted": True,
            "desc": "RINCON_AssociatedZPUDN",
            "resources": [
                resource.to_dict(remove_nones=True) for resource in resources_list
            ],
        }
        assert didl_object.to_dict(remove_nones=True) == the_dict

    def test_didl_object_to_element(self):
        didl_object = data_structures.DidlObject(
            title="a_title", parent_id="pid", item_id="iid", creator="a_creator"
        )
        # we seem to have to go through this to get ElementTree to deal
        # with namespaces properly!
        elt = XML.fromstring(XML.tostring(didl_object.to_element(True)))
        elt2 = XML.fromstring(
            '<dummy xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            + 'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            + 'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
            + '<item id="iid" parentID="pid" restricted="true">'
            + "<dc:title>a_title</dc:title>"
            + "<dc:creator>a_creator</dc:creator>"
            + '<upnp:class>object</upnp:class><desc id="cdudn" '
            + 'nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
            + "RINCON_AssociatedZPUDN</desc></item></dummy>"
        )[0]
        assert_xml_equal(elt2, elt)


# There is an overview of all observed classes, whether they are in or
# out of base DIDL in official_and_extended_didl_classes.txt


def test_didl_object_inheritance():
    """Test that DIDL object inheritance is as indicated by the didl class"""
    class_dict = data_structures._DIDL_CLASS_TO_CLASS.copy()
    class_dict["object"] = data_structures.DidlObject
    for didl_class, soco_class in data_structures._DIDL_CLASS_TO_CLASS.items():
        # Skip this one, because its DIDL class is expected to be an error
        if didl_class == "object.itemobject.item.sonos-favorite":
            continue
        # object does not inherit
        if didl_class == "object":
            continue

        # First make sure it is registered with the correct DIDL class
        assert didl_class == soco_class.item_class

        base_didl_class = ".".join(didl_class.split(".")[:-1])
        base_class = data_structures._DIDL_CLASS_TO_CLASS[base_didl_class]
        assert base_class == soco_class.__bases__[0]
