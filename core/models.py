from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

def avatar_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'avatars/{instance.id}.{ext}'

def cover_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'covers/{instance.id}.{ext}'

class University(models.Model):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self):
        return self.name

class CustomUser(AbstractUser):
    university = models.ForeignKey(University, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    avatar = models.ImageField(upload_to=avatar_upload_path, null=True, blank=True)
    cover_image = models.ImageField(upload_to=cover_upload_path, null=True, blank=True)
    bio = models.TextField(blank=True, default='')
    location = models.CharField(max_length=120, blank=True, default='')
    website = models.URLField(blank=True, default='')
    is_verified = models.BooleanField(default=False)
    is_private = models.BooleanField(default=False)

    def __str__(self):
        return self.username

class Question(models.Model):
    description = models.TextField()
    tags = models.CharField(max_length=255, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="questions", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.description[:50] + "..." if len(self.description) > 50 else self.description

class Answer(models.Model):
    content = models.TextField()
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="answers")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Answer by {self.author.username}"

class Reply(models.Model):
    content = models.TextField()
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="replies")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply by {self.author.username}"

class Like(models.Model):
    VOTE_TYPES = (
        ('upvote', 'Upvote'),
        ('downvote', 'Downvote'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, null=True, blank=True, on_delete=models.CASCADE)
    answer = models.ForeignKey(Answer, null=True, blank=True, on_delete=models.CASCADE)
    reply = models.ForeignKey(Reply, null=True, blank=True, on_delete=models.CASCADE)
    vote_type = models.CharField(max_length=10, choices=VOTE_TYPES, default='upvote')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [
            ('user', 'question'),
            ('user', 'answer'),
            ('user', 'reply'),
        ]

    def __str__(self):
        return f"{self.vote_type} by {self.user.username}"

class Notification(models.Model):
    NOTIFICATIONS_TYPE = (
        ('like', 'Like'),
        ('answer', 'Answer'),
        ('reply', 'Reply'),
        ('follow', 'Follow'),
        ('new_question', 'New Question'),
        ('mention', 'Mention'),
    )
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_notifications")
    notification_type = models.CharField(max_length=20, choices=NOTIFICATIONS_TYPE)
    question = models.ForeignKey(Question, null=True, blank=True, on_delete=models.CASCADE)
    answer = models.ForeignKey(Answer, null=True, blank=True, on_delete=models.CASCADE)
    reply = models.ForeignKey(Reply, null=True, blank=True, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.notification_type} from {self.sender.username}"


class LoginSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='login_sessions')
    device = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    logged_in_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.device}"


class Follow(models.Model):
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'following')
        indexes = [
            models.Index(fields=['follower', 'created_at']),
            models.Index(fields=['following', 'created_at']),
            models.Index(fields=['follower', 'following']),
        ]

    def __str__(self):
        return f"{self.follower.username} -> {self.following.username}"


class UserSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_sessions')
    device_name = models.CharField(max_length=255, default='Unknown')
    browser = models.CharField(max_length=100, default='Unknown')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    token = models.TextField(unique=True)
    refresh_token = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_activity']

    def __str__(self):
        return f"{self.user.username} - {self.device_name} - {self.browser}"


class Repost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reposts')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='reposts')
    quote_text = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'question')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} reposted {self.question.id}"


class SearchQuery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='search_queries')
    query = models.CharField(max_length=180)
    normalized_query = models.CharField(max_length=180, db_index=True)
    results_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['normalized_query', 'created_at']),
        ]

    def __str__(self):
        return self.query


class Mention(models.Model):
    mentioned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mentions_made')
    mentioned_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mentions_received')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='mentions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('mentioned_user', 'question')
        indexes = [
            models.Index(fields=['mentioned_user', 'created_at']),
            models.Index(fields=['question', 'mentioned_user']),
        ]

    def __str__(self):
        return f"@{self.mentioned_user.username} in {self.question_id}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.email}"


class SavedQuestion(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='saved_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'question')
        ordering = ['-created_at']


class BlockedUser(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')

class NotInterestedQuestion(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='not_interested')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='not_interested_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'question')

class ReportedQuestion(models.Model):
    REPORT_REASONS = (
        ('spam', 'Spam'),
        ('inappropriate', "Noto'g'ri kontent"),
        ('misleading', "Yolg'on ma'lumot"),
        ('other', 'Boshqa'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reported_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='reports')
    reason = models.CharField(max_length=20, choices=REPORT_REASONS, default='other')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'question')
