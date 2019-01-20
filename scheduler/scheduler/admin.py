from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import ScheduleBoardItem, SchedulerLog

class BoardAdmin(admin.ModelAdmin):
    list_display = ["pretty_name","link_to_log"]
    def link_to_log(self, obj):
        if obj.log is not None:
            link=reverse("admin:scheduler_schedulerlog_change", args=[obj.log.id]) #model name has to be lowercase
            return format_html('<a href="{}">{}</a>'.format(link,obj.log.id))
        else:
            return '-'
    link_to_log.short_description = 'Edit Log'

admin.register(ScheduleBoardItem)(BoardAdmin)
admin.register(SchedulerLog)(admin.ModelAdmin)