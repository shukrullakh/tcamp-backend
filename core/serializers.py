from rest_framework import serializers
from .models import Question, Answer, Reply, Notification, University, Like
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name', 'university']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email'),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            university=validated_data.get('university'),
        )
        return user


class LoginSerializer(serializers.Serializer):
    email_or_username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email_or_username = data.get('email_or_username')
        password = data.get('password')

        user = User.objects.filter(email=email_or_username).first()
        if not user:
            user = User.objects.filter(username=email_or_username).first()

        if user is None:
            raise serializers.ValidationError('User not found')
        if not user.check_password(password):
            raise serializers.ValidationError('Incorrect password')

        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            }
        }


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'bio',
            'location', 'website', 'avatar', 'cover_image', 'is_staff',
            'is_verified', 'is_private', 'date_joined'
        ]

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        url = obj.avatar.url
        request = self.context.get('request')
        return f"{settings.SITE_URL}{obj.avatar.url}" if request else url

    def get_cover_image(self, obj):
        if not obj.cover_image:
            return None
        url = obj.cover_image.url
        request = self.context.get('request')
        return f"{settings.SITE_URL}{obj.cover_image.url}" if request else url


class ReplySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = '__all__'

    def get_likes_count(self, obj):
        return Like.objects.filter(reply=obj).count()


class AnswerSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    replies = ReplySerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = Answer
        fields = '__all__'

    def get_likes_count(self, obj):
        return Like.objects.filter(answer=obj).count()


class QuestionSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    answers = AnswerSerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()
    reposts_count = serializers.SerializerMethodField()
    description = serializers.CharField(trim_whitespace=False)

    class Meta:
        model = Question
        fields = '__all__'

    def get_likes_count(self, obj):
        return Like.objects.filter(question=obj).count()

    def get_reposts_count(self, obj):
        return obj.reposts.count()


class NotificationSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = '__all__'