from django.db import models
from django.utils import timezone

class SchedulerLog(models.Model):
    log = models.TextField(max_length=10240)

class ScheduleBoardItem(models.Model):
    PROCESSING = 'PR'
    IN_QUEUE = 'IQ'
    FINISHED= 'FN'
    KILLED = 'KL'
    TASK_STATES = (
        (PROCESSING, 'Processing'),
        (IN_QUEUE, 'In Queue'),
        (FINISHED, 'Finished'),
        (KILLED, 'Killed'),
    )

    XILINX = 'XL'
    FPGA = 'FP'
    FPGA_TIME_SENSITIVE = 'FT'
    TASK_CHOICES = (
        (XILINX, 'XILINX'),
        (FPGA, 'FPGA'),
        (FPGA_TIME_SENSITIVE, 'FPGA Time Sensitive'),
    )

    environment_file = models.CharField(default='', max_length=256, blank=True, null=True)
    extra_environment = models.TextField(default='', max_length=1024, blank=True, null=True)
    command = models.CharField(default='', max_length=256)
    working_dir = models.CharField(default='', max_length=256)
    priority = models.IntegerField(default=0, blank=True, null=False)
    kind_of_task = models.CharField(choices=TASK_CHOICES, max_length=2, default=XILINX, blank=True)
    state = models.CharField(choices=TASK_STATES, max_length=2, default=IN_QUEUE, blank=True)
    log = models.ForeignKey(SchedulerLog, default=None, on_delete=models.SET_NULL, blank=True, null=True)
    pid = models.IntegerField(default=0, null=True, blank=True)
    started = models.DateTimeField(default=None, null=True, blank=True)
    finished = models.DateTimeField(default=None, null=True, blank=True)

    @property
    def pretty_name(self):
        time = '--'
        if self.state == self.PROCESSING:
            time = self.pretty_date(self.started)
        elif self.state == self.FINISHED:
            time = self.pretty_date(self.finished)
        return '{}---{}---{}---{}'.format(self.command,self.get_kind_of_task_display(),self.get_state_display(),time)

    def summary(self):
        dots = ''
        if len(self.body) > 100:
            dots = '...'
        return self.body[:100] + dots

    def pretty_date(self, date):
        return date.strftime('%Y-%m-%d: %H-%M-%S')

    def mark_as_finished(self, log):
        self.state = self.FINISHED
        self.finished = timezone.now()
        self.log = log
        self.pid = 0
        self.save()

    def mark_as_killed(self):
        self.state = self.KILLED
        self.finished = timezone.now()
        self.pid = 0
        self.save()


    def mark_as_processing(self, log):
        self.state = self.PROCESSING
        self.started = timezone.now()
        self.log = log
        self.save()


