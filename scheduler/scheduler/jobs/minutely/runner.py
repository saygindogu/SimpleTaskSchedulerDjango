import logging
from django.conf import settings
import os
import shlex
import subprocess
from django.utils import timezone
from datetime import timedelta
import iso8601
from googleapiclient.discovery import build
from scheduler.models import ScheduleBoardItem, SchedulerLog
from scheduler.views import kill_process

TIME_WINDOW_HRS = 24
MAX_RESULTS = 30

fmt = getattr(settings, 'LOG_FORMAT', None)
lvl = getattr(settings, 'LOG_LEVEL', logging.INFO)

logging.basicConfig(format=fmt, level=lvl)

def run():
    j = Job()
    j.execute()

class Job():
    help = "My sample job."

    os_env = None

    def execute(self):
        print("Current Working Directory ", os.getcwd())
        self.cwd = os.getcwd()
        self.kill_old_tasks()
        current_task = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.IN_QUEUE).order_by('-priority','pk').first()
        processing_tasks = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING)

        if current_task is not None and self.should_run(processing_tasks, current_task):
            logging.info("Running!")
            self.create_calendar_entry(current_task)
            self.save_old_os_env()
            log = SchedulerLog.objects.create(log='Process is running\n')
            current_task.mark_as_processing(log)
            if(current_task.environment_file is not None and current_task.environment_file != ''):
                self.source_bash(current_task.environment_file)
            if(current_task.extra_environment is not None and current_task.extra_environment != ''):
                self.set_os_env(current_task.extra_environment)
            os.chdir(current_task.working_dir)
            p = subprocess.Popen(shlex.split(current_task.command), stdout=subprocess.PIPE, shell=True)
            current_task.pid = p.pid
            current_task.save()
            out, error = p.communicate()
            log.log += out.decode('utf-8')
            log.save()
            current_task.mark_as_finished(log)
            self.restore_old_os_env()
            logging.info(log.log)
            os.chdir(self.cwd)
            self.shorten_calendar_event(current_task)

    def should_run(self, processing_tasks, current_task):
        if not self.calendar_is_ok(delta_hours=current_task.timeslot_duration):
            return False
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
        print("DEBUG TASK METHOD IS CALLED")
        ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.FINISHED).update(state=ScheduleBoardItem.IN_QUEUE)
        ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING).update(state=ScheduleBoardItem.IN_QUEUE)
        has_processing = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING).exists()
        task = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.IN_QUEUE).order_by('pk').first()
        return task, has_processing

    def get_google_calendar_creds(self):
        import pickle
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        creds = None
        # If there are no (valid) credentials available, let the user log in.
        """if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server()
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)"""
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
        return creds

    def shorten_calendar_event(self, task):
        import pprint
        events = self.get_events_around_now()
        if events:
            for event in events:
                summary = event['summary']
                tokens = summary.split(' ')

                if tokens[4].split(':')[0] == 'TaskID' and tokens[4].split(':')[1] == str(task.id):
                    event_id = event['id']
                    creds = self.get_google_calendar_creds()
                    service = build('calendar', 'v3', credentials=creds)

                    event['end'] = {
                            'dateTime': timezone.now().isoformat(),
                            'timeZone': 'Turkey'
                        }

                    event = service.events().update(
                        calendarId='pv5h623hfupri83hv8scd64bqk@group.calendar.google.com',
                        eventId=event_id,
                        body=event).execute()
                    print('Event updated: %s' % (event.get('htmlLink')))


    def calendar_is_ok(self, delta_hours=0):
        events = self.get_events_around_now()

        value = False
        if events:
            for event in events:
                value = value or self.event_conflicts_in_planned_duration(event, delta_hours)

        return not value

    def get_events_around_now(self):
        creds = self.get_google_calendar_creds()
        service = build('calendar', 'v3', credentials=creds)
        # Call the Calendar API
        now = timezone.now()
        then = now - timedelta(hours=TIME_WINDOW_HRS)
        then_str = then.isoformat()
        print('then:', then_str)
        print('Getting the upcoming {} events'.format(MAX_RESULTS))
        events_result = service.events().list(calendarId='pv5h623hfupri83hv8scd64bqk@group.calendar.google.com',
                                              timeMin=then_str,
                                              maxResults=MAX_RESULTS, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        return events

    def event_conflicts_in_planned_duration(self, event, delta_hours=0):
        import pytz
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        aware_dt_start = iso8601.parse_date(start).astimezone(pytz.utc)  # some aware datetime object
        aware_dt_end = iso8601.parse_date(end).astimezone(pytz.utc)  # some aware datetime object
        now = timezone.now()
        planned_end = timezone.now() + timedelta(hours=delta_hours)

        case1 = now <= aware_dt_start and planned_end >= aware_dt_start and planned_end <= aware_dt_end and planned_end >= aware_dt_start
        case2 = planned_end >= aware_dt_start and planned_end <= aware_dt_end and now >= aware_dt_start and now <= aware_dt_end
        case3 = now >= aware_dt_start and now <= aware_dt_end and planned_end >= aware_dt_end

        print('c1',case1)
        print('c2',case2)
        print('c3',case3)
        return case1 or case2 or case3



    def create_calendar_entry(self, task):
        creds = self.get_google_calendar_creds()
        service = build('calendar', 'v3', credentials=creds)

        event = {
            'summary': 'Scheduler Tool Created Task: TaskID:{} Duration:{}'.format(task.id, task.timeslot_duration),
            'location': '-',
            'description': 'This task is automatically created by Saygın\'s task scheduler software.',
            'end': {
                'dateTime': (timezone.now() + timedelta(hours=task.timeslot_duration)).isoformat(),
                'timeZone': 'Turkey'
            },
            'start': {
                'dateTime': timezone.now().isoformat(),
                'timeZone': 'Turkey'
            }
        }

        event = service.events().insert(calendarId='pv5h623hfupri83hv8scd64bqk@group.calendar.google.com',
                                        body=event).execute()
        print('Event created: %s' % (event.get('htmlLink')))

    def kill_old_tasks(self):
        running_tasks = ScheduleBoardItem.objects.filter(state=ScheduleBoardItem.PROCESSING).all()
        for task in running_tasks:
            if task.started + timedelta(hours=task.timeslot_duration) <= timezone.now():
                print("KILLING", task.id)
                kill_process(task.id)
                print("KILLED", task.id)



