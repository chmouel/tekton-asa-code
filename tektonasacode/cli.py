#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Chmouel Boudjnah <chmouel@chmouel.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""Tekton asa Code"""
import argparse
import sys

from tektonasacode import main


def run():
    """Console script for tektonasacode."""
    parser = argparse.ArgumentParser()
    parser.add_argument('github_json', help="The full json from Github")
    parser.add_argument('github_token',
                        help="The Github token to do operation with")

    args = parser.parse_args()
    tkaac = main.TektonAsaCode(args.github_token)
    tkaac.main(args.github_json)


if __name__ == "__main__":
    sys.exit(run())  # pragma: no cover
