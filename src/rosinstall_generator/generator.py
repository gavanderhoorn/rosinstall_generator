# Software License Agreement (BSD License)
#
# Copyright (c) 2013, Open Source Robotics Foundation, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Open Source Robotics Foundation, Inc. nor
#    the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior
#    written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import print_function

import copy
import logging
import os
import sys

from rospkg import RosPack, RosStack
from rospkg.environment import ROS_PACKAGE_PATH

from rosinstall_generator.distro import get_distro as _get_wet_distro
from rosinstall_generator.distro import generate_rosinstall as generate_wet_rosinstall
from rosinstall_generator.distro import get_recursive_dependencies as get_recursive_dependencies_of_wet
from rosinstall_generator.distro import get_recursive_dependencies_on as get_recursive_dependencies_on_of_wet
from rosinstall_generator.distro import get_package_names

from rosinstall_generator.dry_distro import get_distro as _get_dry_distro
from rosinstall_generator.dry_distro import generate_rosinstall as generate_dry_rosinstall
from rosinstall_generator.dry_distro import get_recursive_dependencies as get_recursive_dependencies_of_dry
from rosinstall_generator.dry_distro import get_recursive_dependencies_on as get_recursive_dependencies_on_of_dry
from rosinstall_generator.dry_distro import get_stack_names

logger = logging.getLogger('rosinstall_generator')

ARG_ALL_PACKAGES = 'ALL'
ARG_CURRENT_ENVIRONMENT = 'RPP'

class Names(object):
    '''
    Separates a list of names into wet package and dry stack names and resolves variants.
    '''

    def __init__(self, distro_name, names):
        unknown_names = set(names or [])

        # expand special arguments
        _expand_special_args(distro_name, unknown_names)

        self.wet_package_names = set([])
        self.dry_stack_names = set([])
        variant_names = set([])

        # identify wet packages
        if unknown_names:
            wet_distro = get_wet_distro(distro_name)
            for name in unknown_names:
                if name in wet_distro.packages:
                    self.wet_package_names.add(name)
            unknown_names -= self.wet_package_names

        # identify dry stacks/variants
        if unknown_names:
            dry_distro = get_dry_distro(distro_name)
            for name in unknown_names:
                if name in dry_distro.get_stacks(released=True):
                    self.dry_stack_names.add(name)
                if name in dry_distro.variants:
                    variant_names.add(name)
            unknown_names -= self.dry_stack_names
            unknown_names -= variant_names

        if unknown_names:
            print('The following names could not be found and will be ignored: ' + ', '.join(sorted(unknown_names)), file=sys.stderr)

        # resolve variant names into wet package names or dry stack names
        if variant_names:
            wet_distro = get_wet_distro(distro_name)
            for variant_name in variant_names:
                variant_depends = dry_distro.variants[variant_name].get_stack_names()
                for depend in variant_depends:
                    if depend in wet_distro.packages:
                        self.wet_package_names.add(depend)
                    elif depend in dry_distro.stacks:
                        self.dry_stack_names.add(depend)
                    else:
                        raise RuntimeError("The following dependency of variant '%s' could not be found: %s" % (variant_name, depend))


def _expand_special_args(distro_name, names):
    if ARG_ALL_PACKAGES in names:
        names.remove(ARG_ALL_PACKAGES)
        wet_distro = get_wet_distro(distro_name)
        released_package_names, _ = get_package_names(wet_distro)
        names.update(released_package_names)
        dry_distro = get_dry_distro(distro_name)
        released_stack_names, _ = get_stack_names(dry_distro)
        names.update(released_stack_names)

    if ARG_CURRENT_ENVIRONMENT in names:
        names.remove(ARG_CURRENT_ENVIRONMENT)
        names.update(_get_packages_in_environment())


_packages_in_environment = None


def _get_packages_in_environment():
    global _packages_in_environment
    if _packages_in_environment is None:
        if ROS_PACKAGE_PATH not in os.environ or not os.environ[ROS_PACKAGE_PATH]:
            raise RuntimeError("The environment variable '%s' must be set when using '%s'" % (ROS_PACKAGE_PATH, ARG_CURRENT_ENVIRONMENT))
        _packages_in_environment = set([])
        rs = RosStack()
        _packages_in_environment.update(set(rs.list()))
        rp = RosPack()
        _packages_in_environment.update(set(rp.list()))
    return _packages_in_environment


_wet_distro = None
_dry_distro = None


def get_wet_distro(distro_name):
    global _wet_distro
    if _wet_distro is None:
        _wet_distro = _get_wet_distro(distro_name)
    return _wet_distro


def get_dry_distro(distro_name):
    global _dry_distro
    if _dry_distro is None:
        _dry_distro = _get_dry_distro(distro_name)
    return _dry_distro


def generate_rosinstall(distro_name, names,
    deps=False, deps_up_to=None, deps_only=False,
    wet_only=False, dry_only=False,
    excludes=None,
    tar=False):
    names = Names(distro_name, names)
    if names:
        logger.debug('Names: %s' % ', '.join(sorted(names.wet_package_names | names.dry_stack_names)))
    deps_up_to_names = Names(distro_name, deps_up_to)
    if not names.wet_package_names and not names.dry_stack_names:
        raise RuntimeError('No packages specified')
    if deps_up_to:
        logger.debug('Dependencies up to: %s' % ', '.join(sorted(deps_up_to_names.wet_package_names | deps_up_to_names.dry_stack_names)))
    exclude_names = Names(distro_name, excludes)
    if excludes:
        logger.debug('Excluded packages: %s' % ', '.join(sorted(exclude_names.wet_package_names | exclude_names.dry_stack_names)))

    result = copy.deepcopy(names)
    # clear wet packages if not requested
    if dry_only:
        result.wet_package_names.clear()
    # clear dry packages if not requested and no dependencies
    if wet_only and not deps and not deps_up_to:
        result.dry_stack_names.clear()

    # remove excluded names from the list of wet and dry names
    result.wet_package_names -= set(exclude_names.wet_package_names)
    result.dry_stack_names -= set(exclude_names.dry_stack_names)
    if not result.wet_package_names and not result.dry_stack_names:
        raise RuntimeError('No packages left after applying the exclusions')

    if result.wet_package_names:
        logger.debug('wet package names: %s' % ', '.join(sorted(result.wet_package_names)))
    if result.dry_stack_names:
        logger.debug('dry stack names: %s' % ', '.join(sorted(result.dry_stack_names)))

    # extend the names with recursive dependencies
    if deps or deps_up_to:
        # add dry dependencies
        if result.dry_stack_names:
            dry_distro = get_dry_distro(distro_name)
            _, unreleased_stack_names = get_stack_names(dry_distro)
            excludes = exclude_names.dry_stack_names | deps_up_to_names.dry_stack_names | set(unreleased_stack_names)
            dry_dependencies, wet_dependencies = get_recursive_dependencies_of_dry(dry_distro, result.dry_stack_names, excludes=excludes)
            logger.debug('dry stack names including dependencies: %s' % ', '.join(sorted(dry_dependencies)))
            result.dry_stack_names |= dry_dependencies

            if not dry_only:
                # add wet dependencies of dry stuff
                logger.debug('wet dependencies of dry stacks: %s' % ', '.join(sorted(wet_dependencies)))
                for depend in wet_dependencies:
                    if depend in exclude_names.wet_package_names or depend in deps_up_to_names.wet_package_names:
                        continue
                    wet_distro = get_wet_distro(distro_name)
                    assert depend in wet_distro.packages, 'Package "%s" does not have a version"' % depend
                    result.wet_package_names.add(depend)
        # add wet dependencies
        if result.wet_package_names:
            wet_distro = get_wet_distro(distro_name)
            _, unreleased_package_names = get_package_names(wet_distro)
            excludes = exclude_names.wet_package_names | deps_up_to_names.wet_package_names | set(unreleased_package_names)
            result.wet_package_names |= get_recursive_dependencies_of_wet(wet_distro, result.wet_package_names, excludes=excludes)
            logger.debug('wet package names including dependencies: %s' % ', '.join(sorted(result.wet_package_names)))

    # intersect result with recursive dependencies on
    if deps_up_to:
        # intersect with wet dependencies on
        if deps_up_to_names.wet_package_names:
            wet_distro = get_wet_distro(distro_name)
            result.wet_package_names &= get_recursive_dependencies_on_of_wet(wet_distro, deps_up_to_names.wet_package_names, excludes=names.wet_package_names, limit=result.wet_package_names)
        else:
            result.wet_package_names.clear()
        logger.debug('wet_package_names after intersection: %s' % ', '.join(sorted(result.wet_package_names)))

        # intersect with dry dependencies on
        dry_dependency_names = result.wet_package_names | deps_up_to_names.dry_stack_names
        if dry_dependency_names and not wet_only:
            dry_distro = get_dry_distro(distro_name)
            result.dry_stack_names &= get_recursive_dependencies_on_of_dry(dry_distro, dry_dependency_names, excludes=names.dry_stack_names, limit=result.dry_stack_names)
        else:
            result.dry_stack_names.clear()
        logger.debug('dry_stack_names after intersection: %s' % ', '.join(sorted(result.dry_stack_names)))

    # exclude passed in names
    if deps_only:
        result.wet_package_names -= set(names.wet_package_names)
        result.dry_stack_names -= set(names.dry_stack_names)

    # get wet and/or dry rosinstall data
    rosinstall_data = []
    if not dry_only and result.wet_package_names:
        wet_distro = get_wet_distro(distro_name)
        wet_rosinstall_data = generate_wet_rosinstall(wet_distro, result.wet_package_names, tar=tar)
        rosinstall_data += wet_rosinstall_data
    if not wet_only and result.dry_stack_names:
        dry_distro = get_dry_distro(distro_name)
        dry_rosinstall_data = generate_dry_rosinstall(dry_distro, result.dry_stack_names)
        rosinstall_data += dry_rosinstall_data
    return rosinstall_data


def sort_rosinstall(rosinstall_data):
    def _rosinstall_compare(a, b):
        a_key = a.keys()[0]
        b_key = b.keys()[0]
        a_name = a[a_key]['local-name']
        b_name = b[b_key]['local-name']
        if a_name < b_name:
            return -1
        if a_name > b_name:
            return 1
        return 0
    return sorted(rosinstall_data, _rosinstall_compare)
