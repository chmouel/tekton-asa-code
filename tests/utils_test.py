"""Test when processing templates"""
# pylint: disable=redefined-outer-name,too-few-public-methods
import subprocess

import yaml
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


def test_get_errors():
    """Test get_errors"""
    tools = utils.Utils()

    text = """I have failed to do
what my love would want
my error my mistake"""
    output = tools.get_errors(text)
    assert "**failed**" in output
    assert "**error**" in output
    assert "my love" not in output

    assert not tools.get_errors("Happy as a cucumber")


def test_kubectl_get():
    """Test kubectl_get"""
    tools = utils.Utils()

    # pylint: disable=unused-argument
    def my_execute(command, check_error=""):
        item = yaml.safe_dump({
            "items": [{
                "metadata": {
                    "namespace": "random",
                    "name": "hello"
                }
            }]
        })
        return subprocess.run(f"""echo "{item}" """,
                              shell=True,
                              check=True,
                              capture_output=True)

    tools.execute = my_execute
    output = tools.kubectl_get(obj="none", output_type="yaml")
    assert 'items' in output
    assert 'namespace' not in output['items'][0]['metadata']
