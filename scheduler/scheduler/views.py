from django.http import HttpResponse
import psutil
from scheduler.models import ScheduleBoardItem
import time

def current_datetime(request, board_item_id):
    board_item = ScheduleBoardItem.objects.get(id=board_item_id)
    if board_item.pid == 0:
        html = "<html><body>Item {} is not running. (pid: {}).</body></html>".format(board_item_id, board_item.pid)
    else:
        html = "<html><body>Killed {} (pid: {}).</body></html>".format(board_item_id, board_item.pid)
        parent = psutil.Process(board_item.pid)
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
        time.sleep(1)
        board_item.mark_as_killed()

    return HttpResponse(html)