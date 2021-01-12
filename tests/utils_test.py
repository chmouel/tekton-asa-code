"""Test when processing templates"""
# pylint: disable=redefined-outer-name,too-few-public-methods
from tektonasacode import utils


def test_kapply():
    """Test kapply utils"""
    tests = [
        ("""foo: {{allo}}""", {
            'allo': 'maman'
        }, "foo: maman"),
        ("""foo: {{allo.maman}}""", {
            'allo': {
                'maman': 'bobo'
            }
        }, "foo: bobo"),
        ("""foo: {{allo.maman}}""", {
            'allo': {
                'maman': ['jai', 'bobo']
            }
        }, "foo: ['jai', 'bobo']"),
        ("""foo: {{allo.maman}}""", {
            'allo': {
                'maman': [{
                    'jai': 'bobo',
                    'jveux': 'manger'
                }]
            }
        }, "foo: [{'jai': 'bobo', 'jveux': 'manger'}]"),
    ]
    for test in tests:
        tools = utils.Utils()
        _, res = tools.kapply(test[0], test[1], [], name="test")
        assert res == test[2]
