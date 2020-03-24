#!/usr/bin/env python

import os
import distutils.log

from distutils.core import setup
from distutils.command.install import install
from errno import EEXIST
from monitor_tools import __version__
from monitor_tools import _ConfDir, _ConfFile
from monitor_tools import _StateDir, _LogDir

wrapper_script = 'monitor'
wrapper_aliases = ['monitord']


class monitor_install(install):
    def run(self):
        # Run the default setup tasks
        install.run(self)
        # Now, on POSIX platforms, create the symlinks to the wrapper script
        if os.name == 'posix':
            curr_dir = os.getcwd()
            distutils.log.info('performing post-install operations...')
            os.chdir(self.install_scripts)
            distutils.log.info('creating required symlinks in %s',
                               self.install_scripts)
            for alias in wrapper_aliases:
                distutils.log.info('symlinking %s -> %s',
                                   wrapper_script, alias)
                try:
                    os.symlink(wrapper_script, alias)
                except OSError as e:
                    if e.errno != EEXIST:
                        raise
            os.chdir(curr_dir)
            distutils.log.info('post-install operations completed')


setup(name='monitor_tools',
      version=__version__,
      packages=['monitor_tools'],
      scripts=[wrapper_script],
      cmdclass={"install": monitor_install},
      data_files=[(_ConfDir, [_ConfFile]),
                  (_StateDir, []),
                  (_LogDir, [])])
