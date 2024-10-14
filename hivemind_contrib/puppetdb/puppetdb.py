# This file includes contributions covered by the following licence:
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Daniel Lawrence
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


class Puppetdb:
    def __init__(
        self,
        hostname,
        port,
        api_version,
        query=None,
        environment=None,
        ssl_key=None,
        ssl_cert=None,
        timeout=20,
    ):
        from pypuppetdb import connect

        self.db = connect(
            host=hostname,
            port=port,
            ssl_key=ssl_key,
            ssl_cert=ssl_cert,
            api_version=api_version,
            timeout=timeout,
        )
        self.db.resources = self.db.resources
        self.environment = environment
        if query is None:
            query = {}
        self.query = query

    @staticmethod
    def cmp(comparator, key, value):
        return f'["{comparator}", "{key}", "{value}"]'

    @classmethod
    def regex(cls, key, value):
        return cls.cmp('~', key, value)

    @classmethod
    def equals(cls, key, value):
        return cls.cmp('=', key, value)

    @staticmethod
    def and_(parts):
        return '["and", {}]'.format(", ".join(parts))

    @staticmethod
    def or_(parts):
        return '["or", {}]'.format(", ".join(parts))

    def query_string(self, **kwargs):
        query_parts = []
        for name, value in kwargs.items():
            query_parts.append(self.equals(name, value))
        return self._and(query_parts)

    def query_resources(self, query):
        return self.db.resources(query=query, environment=self.environment)

    def get_nodes_for_resource(self, query):
        """Get all the nodes for a particular resource from puppetdb."""
        self.nodes = set()
        for resource in self.query_resources(query):
            self.nodes.add(resource.node)
        return sorted(self.nodes)
