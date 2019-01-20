from django_extensions.management.jobs import MinutelyJob
import logging
from django.conf import settings
from scheduler.models import SchedulerLog, ScheduleBoardItem
import os
import pprint
import shlex
import subprocess

fmt = getattr(settings, 'LOG_FORMAT', None)
lvl = getattr(settings, 'LOG_LEVEL', logging.INFO)

logging.basicConfig(format=fmt, level=lvl)

def run():
    j = Job()
    j.execute()

class Job(MinutelyJob):
    help = "My sample job."

    os_env = None

    def execute(self):
        current_task = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.IN_QUEUE).order_by('pk').first()
        processing_tasks = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING)

        if self.should_run(processing_tasks, current_task):
            logging.info("Running!")
            self.save_old_os_env()
            log = SchedulerLog.objects.create(log='I touched this, made it running\n')
            current_task.mark_as_processing(log)
            if(current_task.environment_file is not None and current_task.environment_file != ''):
                self.source_bash(current_task.environment_file)
            if(current_task.extra_environment is not None and current_task.extra_environment != ''):
                self.set_os_env(current_task.extra_environment)
            os.chdir(current_task.working_dir)
            p = subprocess.Popen(current_task.command, stdout=subprocess.PIPE, shell=True)
            out, err = p.communicate()
            out = out.decode("utf-8")
            p.wait()
            log.log += out
            log.save()
            current_task.mark_as_finished(log)
            self.restore_old_os_env()
            logging.info(log.log)

    def should_run(self, processing_tasks, current_task):
        if not processing_tasks.exists():
            return True
        if processing_tasks.filter(kind_of_task=ScheduleBoardItem.FPGA_TIME_SENSITIVE).exists():
            return False
        if current_task.kind_of_task == ScheduleBoardItem.FPGA_TIME_SENSITIVE:
            return False

        fpga_processing = processing_tasks.filter(kind_of_task=ScheduleBoardItem.FPGA).exists()
        count_of_xilinx_tasks = processing_tasks.filter(kind_of_task=ScheduleBoardItem.XILINX).count()

        if current_task.kind_of_task == ScheduleBoardItem.FPGA:
            if not fpga_processing:
                return True
        elif current_task.kind_of_task == ScheduleBoardItem.XILINX:
            if count_of_xilinx_tasks <= 1:
                return True
        return False

    def source_bash(self, filename):
        string = "env -i bash -c 'source {} && env'".format(filename)
        command = shlex.split(string)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE)
        out, err = proc.communicate()
        out = out.decode("utf-8")
        self.set_os_env(out)

    def set_os_env(self, str):
        for line in str.split('\n'):
            if line != '':
                (key, value) = line.split("=")
                os.environ[key] = value

    def save_old_os_env(self):
        self.os_env = os.environ

    def restore_old_os_env(self):
        if self.os_env is not None:
            os.environ = self.os_env

    def debug_task(self):
        ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.FINISHED).update(state=ScheduleBoardItem.IN_QUEUE)
        ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING).update(state=ScheduleBoardItem.IN_QUEUE)
        has_processing = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING).exists()
        task = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.IN_QUEUE).order_by('pk').first()
        return task, has_processing


