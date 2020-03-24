# Copyright (c) 2019 Renaissance Computing Institute, except where noted.
# All rights reserved.
#
# This software is released under MIT License
#
# Renaissance Computing Institute,
# (A Joint Institute between the University of North Carolina at Chapel Hill,
# North Carolina State University, and Duke University)
# http://www.renci.org
#
# This software processes the incoming messages on Kafka Topic and configures promethius targets on the fly.
#
# Author: (Komal Thareja kthare10@renci.org)

import os
import json 
import time
import sys
import logging
import logging.handlers

from optparse import OptionParser
from daemon import runner
from threading import Thread
from kafka import *
from monitor_tools import LOGGER

class MonitorCustomizer():

    def __init__(self, kafkahost, kafkaTopic, targetFile = '/opt/prometheus-2.17.0-rc.3.linux-amd64/targets.json'):
        self.firstRun = True
        self.targetFile = targetFile
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/null'
        self.stderr_path = '/dev/null'
        self.stateDir = '/var/lib/monitor'
        self.pidDir = '/var/run'
        self.pidfile_path = (self.pidDir + '/' + "monitor.pid" )
        self.pidfile_timeout = 10000
        self.kafkahost = kafkahost
        self.kafkaTopic = kafkaTopic
        self.batch_size = 1000
        self.running = True

        self.log = logging.getLogger(LOGGER)

        # Need to ensure that the state directory is created.
        if not os.path.exists(self.stateDir):
            os.makedirs(self.stateDir)

        # Ditto for PID directory.
        if not os.path.exists(self.pidDir):
            os.makedirs(self.pidDir)

    def process_message(self, key, value):
        self.log.debug("processing {} {}".format(key, value))
        addTarget = True 
        data = None
        updateTargets = False

        with open(self.targetFile) as json_file:
            data = json.load(json_file)
            for t in data:
                if value in t['targets']:
                    addTarget = False 
                    if key == 'delete':
                        self.log.debug("Deleting target {}".format(t))
                        data.remove(t)
                        updateTargets = True
                        break

        if addTarget:
            target = {}
            target['labels'] = {}
            target['labels']['job'] = 'node'
            target['targets'] = []
            target['targets'].append(value)
            self.log.debug("Adding target {}".format(target))
            data.append(target)
            updateTargets = True

        if updateTargets:
            with open(self.targetFile, 'w') as jsonfile:
                json.dump(data, jsonfile, indent=4)

    def consume(self):
        try:
            self.log.debug("Consume thread started")
            self.consumer = KafkaConsumer(bootstrap_servers=[self.kafkahost],
                                  api_version=(0, 10),
                                  auto_offset_reset='earliest',
                                  enable_auto_commit=True)

            topics = [self.kafkaTopic]
            self.consumer.subscribe(topics)
            while self.running:
                try:
                    records = self.consumer.poll(1)
                    # There were no messages on the queue, continue polling
                    if records is None:
                        continue
                    for partition, msgs in records.items():
                        for m in msgs:
                            self.process_message(m.key, m.value)
                except Exception as e:
                    self.log.debug("Exception occurred: {}".format(e))
                    continue
                except KeyboardInterrupt:
                    break

            self.log.debug("Shutting down consumer..")
            self.consumer.close()
        except Exception as e:
            self.log.debug("Exception occurred in consumer thread: {}".format(e))

    def configureTargets(self):
        self.log.debug("configureTargets")
        consume_thread = Thread(target=self.consume)
        consume_thread.setDaemon(True)
        consume_thread.start()

    def run(self):
        while True:
            try:
                self.log.debug('Polling')
                if self.firstRun:
                    self.configureTargets()
                self.firstRun = False
                time.sleep(10)
            except KeyboardInterrupt:
                self.log.error('Terminating on keyboard interrupt...')
                sys.exit(0)
            except Exception as e:
                self.log.exception(('Caught exception in daemon loop; ' +
                                    'backtrace follows.'))
                self.log.error('Exception was of type: %s' % (str(type(e))))
            time.sleep(60)

    def cleanup(self):
        self.log.debug("Cleanup done!")
        self.running = False

def main():
    usagestr = 'Usage: %prog start|stop|restart options'
    parser = OptionParser(usage=usagestr)
    parser.add_option(
        '-k',
        '--kafkahost',
        dest='kafkahost',
        type = str,
        help='kafkahost'
    )
    parser.add_option(
        '-t',
        '--kafkatopic',
        dest='kafkatopic',
        type=str,
        help='kafkatopic'
    )

    options, args = parser.parse_args()

    if len(args) != 1:
        parser.print_help()
        sys.exit(1)

    if args[0] == 'start':
        sys.argv = [sys.argv[0], 'start']
    elif args[0] == 'stop':
        sys.argv = [sys.argv[0], 'stop']
    elif args[0] == 'restart':
        sys.argv = [sys.argv[0], 'restart']
    else:
        parser.print_help()
        sys.exit(1)


    initial_log_location = '/dev/tty'
    try:
    	logfd = open(initial_log_location, 'r')
    except:
	initial_log_location = '/dev/null'
    else:
	logfd.close()

    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(format=log_format, filename=initial_log_location)
    log = logging.getLogger(LOGGER)
    log.setLevel('DEBUG')

    app = MonitorCustomizer(options.kafkahost, options.kafkatopic)
    daemon_runner = runner.DaemonRunner(app)

    try:

        log_dir = "/var/log/monitor/"
        log_level = "DEBUG"
        log_file = "monitor.log"
        log_retain = 5
        log_file_size = 5000000
        log_level = 'DEBUG'

        if not os.path.exists(log_dir):
             os.makedirs(log_dir)

        handler = logging.handlers.RotatingFileHandler(
                 log_dir + '/' + log_file,
                 backupCount=log_retain,
                 maxBytes=log_file_size)
        handler.setLevel(log_level)
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)

        log.addHandler(handler)
        log.propagate = False
        log.info('Logging Started')

        daemon_runner.daemon_context.files_preserve = [
                 handler.stream,
             ]

        log.info('Administrative operation: %s' % args[0])
        daemon_runner.do_action()
        log.info('Administrative after action: %s' % args[0])

        if args[0] == 'stop':
            app.cleanup()

    except runner.DaemonRunnerStopFailureError as drsfe:
        log.propagate = True
        log.error('Unable to stop service; reason was: %s' % str(drsfe))
        log.error('Exiting...')
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
