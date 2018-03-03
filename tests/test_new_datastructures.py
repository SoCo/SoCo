# -*- coding: utf-8 -*-
"""Module to test the data structure classes with pytest."""

from __future__ import unicode_literals

import pytest

from soco import data_structures
from soco.exceptions import DIDLMetadataError
from soco.xml import XML


@pytest.fixture
def didl_object():
    return data_structures.DidlObject(
        title='a_title',
        parent_id='pid',
        item_id='iid',
        creator='a_creator',
        write_status='wstatus',
    )


@pytest.fixture
def didl_object_dict():
    return {
        'title': 'a_title',
        'parent_id': 'pid',
        'item_id': 'iid',
        'creator': 'a_creator',
        'write_status': 'wstatus',
        'restricted': True,
        'desc': 'RINCON_AssociatedZPUDN'
    }


@pytest.fixture
def resource():
    return data_structures.DidlResource('a%20uri', 'a:protocol:info:xx')


@pytest.fixture
def resource_dict():
    return {'uri': 'a%20uri', 'protocol_info': 'a:protocol:info:xx'}


def _strip_ns(tag):
    return tag[tag.find('}')+1:]


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
            explain.append('tag <%s> does not match tag <%s>' %
                           (left.tag, right.tag))
        tag = _strip_ns(left.tag)
        for attrib in set(left.attrib) - set(right.attrib):
            explain.append('left element <%s> has attribute %s but right does not' %
                           (tag, attrib))
        for attrib in set(right.attrib) - set(left.attrib):
            explain.append('right element <%s> has attribute %s but left does not' %
                           (tag, attrib))
        for attrib in set(left.attrib) & set(right.attrib):
            if left.get(attrib) != right.get(attrib):
                explain.append('attribute %s for element <%s>: %r != %r' %
                               (attrib, tag, left.get(attrib), right.get(attrib)))
        if left.text != right.text:
            explain.append('text for element <%s>: %r != %r' %
                           (tag, left.text, right.text))
        if left.tail != right.tail:
            explain.append('tail for element <%s>: %r != %r' %
                           (tag, left.tail, right.tail))

        left_childtags = set(child.tag for child in left)
        right_childtags = set(child.tag for child in right)
        for child_tag in left_childtags - right_childtags:
            explain.append('left element <%s> has child <%s> but right does not' %
                           (tag, _strip_ns(child_tag)))
        for child_tag in right_childtags - left_childtags:
            explain.append('right element <%s> has child <%s> but left does not' %
                           (tag, _strip_ns(child_tag)))
        for child_tag in right_childtags & left_childtags:
            _build_explanation(left.find(child_tag), right.find(child_tag),
                               explain)
        return

    explain = []
    _build_explanation(left, right, explain)
    if explain != []:
        header = "Comparing XML elements %s and %s:\n" % (left, right)
        assert False, header + '\n'.join(explain)


class TestResource():
    """Testing the Resource class."""

    def test_create_didl_resource_with_no_params(self):
        with pytest.raises(TypeError):
            res = data_structures.DidlResource()

    def test_create_didl_resource(self):
        res = data_structures.DidlResource('a%20uri', 'a:protocol:info:xx')
        assert res.uri == 'a%20uri'
        assert res.protocol_info == 'a:protocol:info:xx'

    def test_create_didl_resource_to_from_element(self):
        res = data_structures.DidlResource('a%20uri', 'a:protocol:info:xx',
                                           bitrate=3)
        elt = res.to_element()
        assert XML.tostring(elt) == (
            b'<res bitrate="3" protocolInfo="a:protocol:info:xx">a%20uri</res>')
        assert data_structures.DidlResource.from_element(elt) == res

    def test_didl_resource_to_dict(self, resource):
        rez = resource.to_dict()
        assert rez['uri'] == 'a%20uri'
        assert rez['protocol_info'] == 'a:protocol:info:xx'
        assert len(rez) == 12

    def test_didl_resource_to_dict_remove_nones(self, resource, resource_dict):
        rez = resource.to_dict(remove_nones=True)
        assert rez == resource_dict

    def test_didl_resource_to_dict_from_dict(self, resource):
        rez = data_structures.DidlResource.from_dict(resource.to_dict())
        assert resource == rez

    def test_didl_resource_from_dict(self, resource, resource_dict):
        rez = data_structures.DidlResource.from_dict(resource_dict)
        assert resource == rez

    def test_didl_resource_eq(self, resource):
        assert resource != data_structures.DidlObject(
            title='a_title', parent_id='pid', item_id='iid')
        assert resource is not None
        assert resource == resource


class TestDidlObject():
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
            didl_obj = data_structures.DidlObject()

    def test_create_didl_object_with_disallowed_params(self):
        with pytest.raises(ValueError) as excinfo:
            didl_obj = data_structures.DidlObject(
                title='a_title', parent_id='pid', item_id='iid', bad_args='other')
        assert 'not allowed' in str(excinfo.value)

    def test_create_didl_object_with_good_params(self):
        didl_object = data_structures.DidlObject(
            title='a_title',
            parent_id='pid',
            item_id='iid',
            creator='a_creator',
            desc="dummy")
        assert didl_object is not None
        assert didl_object.title == 'a_title'
        assert didl_object.parent_id == 'pid'
        assert didl_object.item_id == 'iid'
        assert didl_object.creator == 'a_creator'
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
        assert didl_object.title == 'the_title'
        assert didl_object.parent_id == 'pid'
        assert didl_object.item_id == 'iid'
        assert didl_object.creator == 'a_creator'
        assert didl_object.desc == 'DUMMY'
        assert didl_object.item_class == 'object'

    def test_didl_object_from_element_unoff_subelement(self):
        """Test that for a DidlObject created from an element with an
        unofficial .# specified sub class, that the sub class is
        completely ignored

        """
        elt = XML.fromstring(
            self.didl_xml.replace('object', 'object.#SubClass')
        )
        didl_object = data_structures.DidlObject.from_element(elt)
        assert didl_object.item_class == 'object'

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
        """)
        with pytest.raises(DIDLMetadataError) as excinfo:
            didl_object = data_structures.DidlObject.from_element(bad_elt1)
        assert ("UPnP class is incorrect. Expected 'object', got 'object.item'"
                ) in str(excinfo.value)

    def test_didl_object_from_dict(self, didl_object, didl_object_dict):
        assert data_structures.DidlObject.from_dict(didl_object_dict) == \
            didl_object
        # adding in an attibute not in _translation should make no difference
        didl_object_dict['creator'] = 'another_creator'
        assert data_structures.DidlObject.from_dict(didl_object_dict) != \
            didl_object
        # round trip
        assert data_structures.DidlObject.from_dict(didl_object_dict).to_dict() == \
            didl_object_dict

    def test_didl_object_from_dict_resources(self, didl_object,
                                             didl_object_dict, resource):
        didl_object.resources = [resource]
        didl_object_dict['resources'] = [resource.to_dict()]
        assert data_structures.DidlObject.from_dict(didl_object_dict) == \
            didl_object

    def test_didl_object_from_dict_resources_remove_nones(self, didl_object,
                                                          didl_object_dict,
                                                          resource):
        didl_object.resources = [resource]
        didl_object_dict['resources'] = [resource.to_dict(remove_nones=True)]
        assert data_structures.DidlObject.from_dict(didl_object_dict) == \
            didl_object

    def test_didl_comparisons(self):
        didl_object_1 = data_structures.DidlObject(
            title='a_title', parent_id='pid', item_id='iid', creator='a_creator')
        didl_object_2 = data_structures.DidlObject(
            title='a_title', parent_id='pid', item_id='iid', creator='a_creator')
        # should be not the same, but equal!
        assert didl_object_1 is not didl_object_2
        assert didl_object_1 == didl_object_2
        didl_object_3 = data_structures.DidlObject(
            title='a_title',
            parent_id='pid',
            item_id='iid',
            creator='a__different_creator')
        assert didl_object_3 != didl_object_1

    def test_didl_object_to_dict(self, didl_object, didl_object_dict):
        assert didl_object.to_dict() == didl_object_dict
        # adding in an attibute not in _translation should make no difference
        didl_object.other = 'other'
        assert didl_object.to_dict() == didl_object_dict
        # but changing on the other should
        didl_object.creator = 'another'
        assert didl_object.to_dict() != didl_object_dict

    def test_didl_object_to_dict_resources(self, didl_object, didl_object_dict,
                                           resource):
        didl_object.resources = [resource]
        didl_object_dict['resources'] = [resource.to_dict()]
        assert didl_object.to_dict() == didl_object_dict

    def test_didl_object_to_dict_resources_remove_nones(self, didl_object,
                                                        didl_object_dict,
                                                        resource):
        didl_object.resources = [resource]
        didl_object_dict['resources'] = [resource.to_dict(remove_nones=True)]
        assert didl_object.to_dict(remove_nones=True) == didl_object_dict

    def test_didl_object_to_element(self, didl_object):
        # we seem to have to go through this to get ElementTree to deal
        # with namespaces properly!
        elt = XML.fromstring(XML.tostring(didl_object.to_element(True)))
        elt2 = XML.fromstring(
            '<dummy xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" ' +
            'xmlns:dc="http://purl.org/dc/elements/1.1/" ' +
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">' +
            '<item id="iid" parentID="pid" restricted="true">' +
            '<dc:title>a_title</dc:title>' +
            '<dc:creator>a_creator</dc:creator>' +
            '<upnp:writeStatus>wstatus</upnp:writeStatus>' +
            '<upnp:class>object</upnp:class><desc id="cdudn" ' +
            'nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">' +
            'RINCON_AssociatedZPUDN</desc></item></dummy>')[0]
        assert_xml_equal(elt2, elt)
