import unittest

from hivemind_contrib import glance


TESTNAME = 'Nectar Test Image Name'
TESTBUILD = '5'


class FakeImage(object):

    def __init__(self, image_id='039d104b7a5c4631b4ba6524d0b9e981',
                 name='FakeImage', **kwargs):
        for k, v in kwargs.items():
            if v:
                setattr(self, k, v)
        self.id = image_id
        self.name = name

    def get(self, v):
        return getattr(self, v, None)


class GlanceTestCase(unittest.TestCase):

    def test_match_no_name(self):
        image = FakeImage()
        result = glance.match(TESTNAME, TESTBUILD, image)
        self.assertFalse(result)

    def test_match_no_build(self):
        image = FakeImage(nectar_name=TESTNAME)
        result = glance.match(TESTNAME, TESTBUILD, image)
        self.assertFalse(result)

    def test_match_lower_build(self):
        image = FakeImage(nectar_name=TESTNAME, nectar_build='4')
        result = glance.match(TESTNAME, TESTBUILD, image)
        self.assertTrue(result)

    def test_match_same_build(self):
        image = FakeImage(nectar_name=TESTNAME, nectar_build=TESTBUILD)
        result = glance.match(TESTNAME, TESTBUILD, image)
        self.assertFalse(result)

    def test_match_higher_build(self):
        image = FakeImage(nectar_name=TESTNAME, nectar_build='6')
        result = glance.match(TESTNAME, TESTBUILD, image)
        self.assertFalse(result)
