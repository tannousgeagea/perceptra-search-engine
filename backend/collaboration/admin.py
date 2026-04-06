from django.contrib import admin
from .models import Comment, Assignment, ActivityEvent


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'content_type', 'object_id', 'created_at')
    list_filter = ('content_type', 'tenant')
    raw_id_fields = ('author',)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('detection', 'assigned_to', 'status', 'priority', 'due_date', 'created_at')
    list_filter = ('status', 'priority', 'tenant')
    raw_id_fields = ('detection', 'assigned_to', 'assigned_by')


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'target_type', 'target_id', 'created_at')
    list_filter = ('action', 'target_type', 'tenant')
    raw_id_fields = ('user',)
