from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets, permissions
from django.db.models import Count, Q, Case, When, Value, IntegerField, Max
from django.utils import timezone
from datetime import timedelta
from difflib import SequenceMatcher
import re
from .models import UserSession, Repost, ContactMessage, SavedQuestion, Question, Answer, Reply, Notification, Like, LoginSession, SearchQuery, Mention
from .serializers import QuestionSerializer, AnswerSerializer, ReplySerializer, NotificationSerializer, RegisterSerializer, LoginSerializer, UserSerializer
from django.contrib.auth import get_user_model
import os

User = get_user_model()

def get_device_name(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'iphone' in ua: return 'iPhone'
    if 'ipad' in ua: return 'iPad'
    if 'android' in ua and 'mobile' in ua: return 'Android telefon'
    if 'android' in ua: return 'Android planshet'
    if 'macintosh' in ua or 'mac os' in ua: return 'Mac kompyuter'
    if 'windows' in ua: return 'Windows kompyuter'
    if 'linux' in ua: return 'Linux kompyuter'
    return "Noma'lum qurilma"

def get_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0]
    return request.META.get('REMOTE_ADDR')


MENTION_RE = re.compile(r'(?<![\w.])@([A-Za-z0-9_]{2,30})')


def sync_question_mentions(question, actor):
    usernames = {
        match.group(1).lower()
        for match in MENTION_RE.finditer(question.description or '')
    }
    if not usernames:
        Mention.objects.filter(question=question).delete()
        return

    mentioned_users = User.objects.filter(username__in=usernames).exclude(id=actor.id)
    Mention.objects.filter(question=question).exclude(mentioned_user__in=mentioned_users).delete()

    for mentioned_user in mentioned_users:
        mention, created = Mention.objects.get_or_create(
            question=question,
            mentioned_user=mentioned_user,
            defaults={'mentioned_by': actor},
        )
        if not created and mention.mentioned_by_id != actor.id:
            mention.mentioned_by = actor
            mention.save(update_fields=['mentioned_by'])
        if created:
            Notification.objects.create(
                recipient=mentioned_user,
                sender=actor,
                notification_type='mention',
                question=question,
            )

class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            email_or_username = request.data.get('email_or_username')
            user = User.objects.filter(email=email_or_username).first()
            if not user:
                user = User.objects.filter(username=email_or_username).first()
            if user:
                device = get_device_name(request)
                ip = get_ip(request)
                LoginSession.objects.create(user=user, device=device, ip_address=ip)
                # UserSession (yangi)
                ua_string = request.META.get('HTTP_USER_AGENT', '')
                device_name, browser = parse_user_agent(ua_string)
                access_token = data.get('access', '')
                refresh_token = data.get('refresh', '')
                UserSession.objects.create(
                    user=user,
                    device_name=device_name,
                    browser=browser,
                    ip_address=ip or None,
                    user_agent=ua_string[:500],
                    token=access_token,
                    refresh_token=refresh_token,
                )
            return Response(data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def get_vote_count(type_, id_, vote_type):
    if type_ == 'question':
        return Like.objects.filter(question_id=id_, vote_type=vote_type, answer_id__isnull=True, reply_id__isnull=True).count()
    elif type_ == 'answer':
        return Like.objects.filter(answer_id=id_, vote_type=vote_type, question_id__isnull=True, reply_id__isnull=True).count()
    elif type_ == 'reply':
        return Like.objects.filter(reply_id=id_, vote_type=vote_type, question_id__isnull=True, answer_id__isnull=True).count()
    return 0


class LikeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        type_ = request.data.get('type')
        id_ = request.data.get('id')
        vote_type = request.data.get('vote_type', 'upvote')

        if not type_ or not id_:
            return Response({'error': 'type va id kerak'}, status=400)

        filters = {'user': user}
        if type_ == 'question':
            filters['question_id'] = id_
        elif type_ == 'answer':
            filters['answer_id'] = id_
        elif type_ == 'reply':
            filters['reply_id'] = id_
        else:
            return Response({'error': "type noto'g'ri"}, status=400)

        existing = Like.objects.filter(**filters).first()
        if existing:
            existing.delete()
            voted = None
        else:
            Like.objects.create(**filters, vote_type='upvote')
            voted = "upvote"

        return Response({
            "voted": voted,
            "upvotes": get_vote_count(type_, id_, 'upvote'),
        })

class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'bio': user.bio,
            'location': user.location,
            'website': user.website,
            'date_joined': user.date_joined,
            'avatar': request.build_absolute_uri(user.avatar.url) if user.avatar else None,
            'cover_image': request.build_absolute_uri(user.cover_image.url) if user.cover_image else None,
            'is_staff': user.is_staff,
            'is_verified': user.is_verified,
            'is_private': user.is_private,
            'followers_count': user.followers.count(),
            'following_count': user.following.count(),
            'questions_count': user.questions.count(),
            'answers_count': user.answers.count(),
        })

    def patch(self, request):
        user = request.user
        user.first_name = request.data.get('first_name', user.first_name)
        user.last_name = request.data.get('last_name', user.last_name)
        user.email = request.data.get('email', user.email)
        user.bio = request.data.get('bio', user.bio)
        user.location = request.data.get('location', user.location)
        user.website = request.data.get('website', user.website)
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
        if 'cover_image' in request.FILES:
            user.cover_image = request.FILES['cover_image']
        user.save()
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'bio': user.bio,
            'location': user.location,
            'website': user.website,
            'date_joined': user.date_joined,
            'avatar': request.build_absolute_uri(user.avatar.url) if user.avatar else None,
            'cover_image': request.build_absolute_uri(user.cover_image.url) if user.cover_image else None,
            'is_verified': user.is_verified,
            'is_private': user.is_private,
            'followers_count': user.followers.count(),
            'following_count': user.following.count(),
            'questions_count': user.questions.count(),
            'answers_count': user.answers.count(),
        })

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current = request.data.get('current_password')
        new_pass = request.data.get('new_password')
        if not request.user.check_password(current):
            return Response({'error': "Joriy parol noto'g'ri"}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_pass) < 8:
            return Response({'error': "Yangi parol kamida 8 ta belgi bo'lishi kerak"}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_pass)
        request.user.save()
        return Response({'message': 'Parol muvaffaqiyatli yangilandi'})

class ChangeUsernameView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_username = request.data.get('new_username')
        if not new_username:
            return Response({'error': "Yangi foydalanuvchi nomi kerak"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=new_username).exists():
            return Response({'error': "Bu foydalanuvchi nomi allaqachon mavjud"}, status=status.HTTP_400_BAD_REQUEST)
        request.user.username = new_username
        request.user.save()
        return Response({'message': 'Foydalanuvchi nomi muvaffaqiyatli yangilandi'})

class LoginSessionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get('session_id')
        if session_id:
            sessions = LoginSession.objects.filter(user=request.user, id=session_id)
        else:
            sessions = LoginSession.objects.filter(user=request.user).order_by('-logged_in_at')[:1]
        return Response([{
            'id': s.id,
            'device': s.device,
            'ip_address': s.ip_address,
            'logged_in_at': s.logged_in_at,
        } for s in sessions])

    def delete(self, request, session_id=None):
        if session_id:
            LoginSession.objects.filter(id=session_id, user=request.user).delete()
            return Response({'message': 'Session tugatildi'})
        # Barcha sessionlarni o'chirish (joriyidan tashqari)
        latest = LoginSession.objects.filter(user=request.user).order_by('-logged_in_at').first()
        if latest:
            LoginSession.objects.filter(user=request.user).exclude(id=latest.id).delete()
        return Response({'message': 'Barcha sessionlar tugatildi'})

class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all().order_by('-created_at')
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        question = serializer.save(author=self.request.user)
        sync_question_mentions(question, self.request.user)
        return question

    def perform_update(self, serializer):
        question = serializer.save()
        sync_question_mentions(question, self.request.user)
        return question

class AnswerViewSet(viewsets.ModelViewSet):
    queryset = Answer.objects.all().order_by('-created_at')
    serializer_class = AnswerSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        return serializer.save(author=self.request.user)

class ReplyViewSet(viewsets.ModelViewSet):
    queryset = Reply.objects.all().order_by('-created_at')
    serializer_class = ReplySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        return serializer.save(author=self.request.user)

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_read = request.data.get('is_read', instance.is_read)
        instance.save()
        return Response(self.get_serializer(instance).data)


class UserProfileView(APIView):
    def get(self, request, username):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)
        
        questions_count = user.questions.count()
        answers_count = user.answers.count()
        
        return Response({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'avatar': request.build_absolute_uri(user.avatar.url) if user.avatar else None,
            'questions_count': questions_count,
            'answers_count': answers_count,
            'date_joined': user.date_joined,
        })


from .models import UserSession, Repost, ContactMessage, SavedQuestion, Follow

class FollowView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, user_id):
        try:
            target = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Foydalanuvchi topilmadi'}, status=404)

        if target == request.user:
            return Response({'error': 'O\'zingizni follow qila olmaysiz'}, status=400)

        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following=target
        )

        if not created:
            follow.delete()
            return Response({'following': False, 'followers_count': target.followers.count()})

        return Response({'following': True, 'followers_count': target.followers.count()})

    def get(self, request, user_id):
        if int(user_id) == request.user.id:
            return Response({'following': False})
        is_following = Follow.objects.filter(
            follower=request.user,
            following_id=user_id
        ).exists()
        return Response({'following': is_following})


class FollowingListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        following_users = User.objects.filter(
            followers__follower=request.user
        ).order_by('username')

        data = []
        for user in following_users:
            avatar_url = None
            if user.avatar:
                avatar_url = request.build_absolute_uri(user.avatar.url)

            data.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'avatar': avatar_url,
                'questions_count': user.questions.count(),
                'answers_count': user.answers.count(),
                'followers_count': user.followers.count(),
            })

        return Response(data)


def get_mutual_followers(user, request):
    if not request.user.is_authenticated:
        return []
    return list(
        User.objects.filter(
            followers__follower=request.user,
            following__following=user,
        )
        .exclude(id__in=[request.user.id, user.id])
        .order_by('username')
        .values_list('username', flat=True)[:3]
    )


def mutual_followers_count(user, request):
    if not request.user.is_authenticated:
        return 0
    return User.objects.filter(
        followers__follower=request.user,
        following__following=user,
    ).exclude(id__in=[request.user.id, user.id]).count()


def serialize_social_user(user, request):
    avatar_url = None
    if user.avatar:
        avatar_url = request.build_absolute_uri(user.avatar.url)
    cover_url = None
    if user.cover_image:
        cover_url = request.build_absolute_uri(user.cover_image.url)
    is_following = False
    follows_viewer = False
    if request.user.is_authenticated:
        is_following = Follow.objects.filter(follower=request.user, following=user).exists()
        follows_viewer = Follow.objects.filter(follower=user, following=request.user).exists()
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'bio': user.bio,
        'location': user.location,
        'website': user.website,
        'avatar': avatar_url,
        'cover_image': cover_url,
        'date_joined': user.date_joined,
        'is_verified': user.is_verified,
        'is_private': user.is_private,
        'is_online': user.user_sessions.filter(is_active=True).exists(),
        'is_following': is_following,
        'follows_viewer': follows_viewer,
        'mutual_followers': get_mutual_followers(user, request),
        'followers_count': user.followers.count(),
        'following_count': user.following.count(),
        'questions_count': user.questions.count(),
        'answers_count': user.answers.count(),
    }


class UserFollowersView(APIView):
    def get(self, request, user_id):
        users = User.objects.filter(following__following_id=user_id).prefetch_related('followers', 'following')
        serialized = [serialize_social_user(user, request) for user in users]
        serialized.sort(key=lambda item: (
            0 if request.user.is_authenticated and item['id'] == request.user.id else 1,
            -len(item.get('mutual_followers') or []),
            item['username'].lower(),
        ))
        return Response(serialized)


class UserFollowingView(APIView):
    def get(self, request, user_id):
        users = User.objects.filter(followers__follower_id=user_id).prefetch_related('followers', 'following')
        serialized = [serialize_social_user(user, request) for user in users]
        serialized.sort(key=lambda item: (
            0 if request.user.is_authenticated and item['id'] == request.user.id else 1,
            -len(item.get('mutual_followers') or []),
            item['username'].lower(),
        ))
        return Response(serialized)


def normalize_search_query(value):
    return " ".join((value or "").strip().lower().replace("#", "").split())[:180]


def topic_payload(topic, query=""):
    slug = normalize_search_query(topic).replace(" ", "")
    label = slug or "campus"
    human = label.replace("-", " ")
    return {
        'tag': f"#{label}",
        'title': human.title(),
        'description': f"Popular {human} questions and discussions",
        'href': f"/?search={label}",
        'score': SequenceMatcher(None, normalize_search_query(query), label).ratio() if query else 0,
    }


class SearchView(APIView):
    def get(self, request):
        raw_query = request.query_params.get('q', '')
        query = normalize_search_query(raw_query)
        limit = min(int(request.query_params.get('limit', 6) or 6), 12)

        recent = []
        if request.user.is_authenticated:
            recent = list(SearchQuery.objects.filter(user=request.user).values_list('query', flat=True).distinct()[:6])

        trending_rows = (
            SearchQuery.objects.filter(created_at__gte=timezone.now() - timedelta(days=14))
            .values('normalized_query')
            .annotate(count=Count('id'), last_seen=Max('created_at'))
            .exclude(normalized_query='')
            .order_by('-count', '-last_seen')[:8]
        )
        trending_searches = [row['normalized_query'] for row in trending_rows]

        if not query:
            return Response({
                'query': raw_query,
                'users': [],
                'questions': [],
                'topics': [topic_payload(topic) for topic in (trending_searches or ['react', 'cybersecurity', 'python', 'design', 'ai'])[:6]],
                'recent_searches': recent,
                'trending_searches': trending_searches,
                'communities': [{'name': f"{topic.title()} Circle", 'tag': f"#{topic.replace(' ', '')}", 'members': 1200 + index * 315} for index, topic in enumerate((trending_searches or ['react', 'cybersecurity', 'ai'])[:4])],
                'suggestions': ['React roadmap', 'Cybersecurity roadmap', 'Best campus projects', 'AI study tools'],
            })

        user_matches = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(bio__icontains=query)
        ).annotate(
            username_rank=Case(
                When(username__iexact=query, then=Value(0)),
                When(username__istartswith=query, then=Value(1)),
                When(username__icontains=query, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
            followers_total=Count('followers', distinct=True),
            questions_total=Count('questions', distinct=True),
        ).order_by('username_rank', '-followers_total', '-questions_total', 'username')[:limit]

        question_matches = Question.objects.filter(
            Q(description__icontains=query) |
            Q(tags__icontains=query) |
            Q(author__username__icontains=query)
        ).select_related('author').annotate(
            answers_total=Count('answers', distinct=True),
            likes_total=Count('like', filter=Q(like__vote_type='upvote'), distinct=True),
            reposts_total=Count('reposts', distinct=True),
        ).order_by('-likes_total', '-answers_total', '-reposts_total', '-created_at')[:limit]

        tags = set()
        for question in question_matches:
            for tag in (question.tags or '').replace(',', ' ').split():
                if query in normalize_search_query(tag):
                    tags.add(normalize_search_query(tag))
        if not tags:
            tags = {query.replace(' ', ''), *[f"{query} roadmap", f"{query} discussions", f"learn {query}"]}

        users = [serialize_social_user(user, request) for user in user_matches]
        questions = [{
            'id': question.id,
            'title': question.description[:90],
            'description': question.description[:180],
            'author': UserSerializer(question.author, context={'request': request}).data,
            'created_at': question.created_at,
            'answers_count': question.answers_total,
            'likes_count': question.likes_total,
            'reposts_count': question.reposts_total,
            'href': f"/question/{question.id}",
        } for question in question_matches]

        total_results = len(users) + len(questions)
        SearchQuery.objects.create(
            user=request.user if request.user.is_authenticated else None,
            query=raw_query[:180],
            normalized_query=query,
            results_count=total_results,
        )

        smart_questions = [
            f"How to learn {query}?",
            f"Best {query} projects",
            f"{query.title()} roadmap",
            f"{query.title()} discussions",
        ]

        return Response({
            'query': raw_query,
            'users': users,
            'questions': questions or [{'title': item, 'description': 'Open a discussion with the campus community', 'href': f"/?search={item}"} for item in smart_questions],
            'topics': [topic_payload(tag, query) for tag in list(tags)[:6]],
            'recent_searches': recent,
            'trending_searches': trending_searches,
            'communities': [{'name': f"{tag.title()} Circle", 'tag': f"#{tag.replace(' ', '')}", 'members': 1200 + index * 315} for index, tag in enumerate(list(tags)[:4])],
            'suggestions': smart_questions,
        })


class MentionSuggestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = normalize_search_query(request.query_params.get('q', ''))
        users = User.objects.exclude(id=request.user.id)
        if query:
            users = users.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )
        users = users.annotate(
            username_rank=Case(
                When(username__istartswith=query, then=Value(0)),
                When(username__icontains=query, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ),
            followers_total=Count('followers', distinct=True),
        ).order_by('username_rank', '-followers_total', 'username')[:8]
        return Response([serialize_social_user(user, request) for user in users])


class UserDetailView(APIView):
    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        followers_count = user.followers.count()
        following_count = user.following.count()
        questions_count = user.questions.count()
        answers_count = user.answers.count()

        is_following = False
        if request.user.is_authenticated:
            is_following = Follow.objects.filter(follower=request.user, following=user).exists()

        avatar_url = None
        if user.avatar:
            avatar_url = request.build_absolute_uri(user.avatar.url)
        cover_url = None
        if user.cover_image:
            cover_url = request.build_absolute_uri(user.cover_image.url)

        return Response({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'bio': user.bio,
            'location': user.location,
            'website': user.website,
            'date_joined': user.date_joined,
            'avatar': avatar_url,
            'cover_image': cover_url,
            'is_verified': user.is_verified,
            'is_private': user.is_private,
            'is_online': user.user_sessions.filter(is_active=True).exists(),
            'followers_count': followers_count,
            'following_count': following_count,
            'questions_count': questions_count,
            'answers_count': answers_count,
            'is_following': is_following,
            'follows_viewer': Follow.objects.filter(follower=user, following=request.user).exists() if request.user.is_authenticated else False,
            'mutual_followers': get_mutual_followers(user, request),
        })


class UserByUsernameView(APIView):
    def get(self, request, username):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)

        request._profile_lookup_user_id = user.id
        return UserDetailView().get(request, user.id)


class SuggestedUsersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        already_following = Follow.objects.filter(
            follower=request.user
        ).values_list('following_id', flat=True)

        exclude_ids = list(already_following) + [request.user.id]

        suggested = User.objects.exclude(id__in=exclude_ids).annotate(
            followers_total=Count('followers', distinct=True),
            questions_total=Count('questions', distinct=True),
            answers_total=Count('answers', distinct=True),
        ).order_by('-followers_total', '-questions_total', '-answers_total', '-date_joined')[:18]

        data = []
        for user in suggested:
            item = serialize_social_user(user, request)
            item['recommendation_reason'] = 'Popular in your campus network' if item['followers_count'] else 'Recently active'
            data.append(item)
        return Response(data)


import requests as req_lib

class AIProxyView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    GROQ_API_URL = os.getenv("GROQ_API_KEY")

    def post(self, request):
        messages = request.data.get('messages', [])
        try:
            res = req_lib.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.GROQ_API_URL}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Sen TCamp platformasining AI yordamchisissan. Talabalar o'qish, dasturlash, fanlar bo'yicha savol berishadi. Javoblarni qisqa, aniq va foydali qil. O'zbek tilida so'rashsa o'zbek tilida, rus tilida so'rashsa rus tilida, ingliz tilida so'rashsa ingliz tilida javob ber."
                        },
                        *messages
                    ],
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
                timeout=30
            )
            return Response(res.json(), status=res.status_code)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


def parse_user_agent(ua_string):
    ua = ua_string.lower()
    # Device
    if 'iphone' in ua:
        device = 'iPhone'
    elif 'ipad' in ua:
        device = 'iPad'
    elif 'android' in ua and 'mobile' in ua:
        device = 'Android Telefon'
    elif 'android' in ua:
        device = 'Android Planshet'
    elif 'macintosh' in ua or 'mac os' in ua:
        device = 'Mac'
    elif 'windows' in ua:
        device = 'Windows PC'
    elif 'linux' in ua:
        device = 'Linux'
    else:
        device = 'Noma\'lam qurilma'

    # Browser
    if 'edg/' in ua or 'edge/' in ua:
        browser = 'Edge'
    elif 'chrome' in ua and 'safari' in ua:
        browser = 'Chrome'
    elif 'firefox' in ua:
        browser = 'Firefox'
    elif 'safari' in ua and 'chrome' not in ua:
        browser = 'Safari'
    elif 'opera' in ua or 'opr/' in ua:
        browser = 'Opera'
    else:
        browser = 'Noma\'lam brauzer'

    return device, browser


class UserSessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sessions = UserSession.objects.filter(user=request.user, is_active=True)
        current_token = str(request.auth)
        data = []
        for s in sessions:
            data.append({
                'id': s.id,
                'device_name': s.device_name,
                'browser': s.browser,
                'ip_address': s.ip_address,
                'created_at': s.created_at,
                'last_activity': s.last_activity,
                'is_current': s.token == current_token,
            })
        return Response(data)


class UserSessionDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, session_id):
        try:
            session = UserSession.objects.get(id=session_id, user=request.user)
            session.is_active = False
            session.save()
            # Refresh tokenni blacklist ga qo'shamiz
            try:
                if session.refresh_token:
                    token = RefreshToken(session.refresh_token)
                    token.blacklist()
            except Exception as e:
                print("Blacklist error:", e)
            return Response({'message': 'Session tugatildi'})
        except UserSession.DoesNotExist:
            return Response({'error': 'Session topilmadi'}, status=404)


class UserSessionLogoutAllView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current_token = str(request.auth)
        sessions = UserSession.objects.filter(
            user=request.user, is_active=True
        ).exclude(token=current_token)
        for session in sessions:
            try:
                if session.refresh_token:
                    token = RefreshToken(session.refresh_token)
                    token.blacklist()
            except Exception as e:
                print("Blacklist error:", e)
        sessions.update(is_active=False)
        return Response({'message': 'Barcha sessionlar tugatildi'})


class RepostView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        question_id = request.data.get('question_id')
        quote_text = (request.data.get('quote_text') or '').strip()
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Savol topilmadi'}, status=404)

        repost, created = Repost.objects.get_or_create(user=request.user, question=question)
        if not created:
            if repost.quote_text != quote_text:
                repost.quote_text = quote_text
                repost.save(update_fields=['quote_text'])
                return Response({'reposted': True, 'quote_text': repost.quote_text, 'reposts_count': question.reposts.count()})
            repost.delete()
            return Response({'reposted': False, 'quote_text': '', 'reposts_count': question.reposts.count()})
        repost.quote_text = quote_text
        repost.save(update_fields=['quote_text'])
        return Response({'reposted': True, 'quote_text': repost.quote_text, 'reposts_count': question.reposts.count()})

    def get(self, request):
        user_id = request.query_params.get('user_id')
        mine_only = request.query_params.get('mine') == '1'
        reposts = Repost.objects.select_related('question', 'question__author', 'user')
        if user_id:
            reposts = reposts.filter(user_id=user_id)
        elif mine_only:
            reposts = reposts.filter(user=request.user)
        else:
            following_ids = list(Follow.objects.filter(follower=request.user).values_list('following_id', flat=True))
            reposts = reposts.filter(Q(user=request.user) | Q(user_id__in=following_ids))
        data = []
        for r in reposts:
            q = r.question
            data.append({
                'timeline_id': f'repost-{r.id}',
                'repost_id': r.id,
                'id': q.id,
                'description': q.description,
                'tags': q.tags,
                'author': UserSerializer(q.author, context={'request': request}).data,
                'created_at': q.created_at,
                'reposted_at': r.created_at,
                'likes_count': q.like_set.filter(vote_type='upvote').count(),
                'upvotes': q.like_set.filter(vote_type='upvote').count(),
                'answers_count': q.answers.count(),
                'reposts_count': q.reposts.count(),
                'is_repost': True,
                'reposted_by': r.user.username,
                'reposted_by_user': UserSerializer(r.user, context={'request': request}).data,
                'quote_text': r.quote_text,
            })
        return Response(data)


class ContactMessageView(APIView):
    def post(self, request):
        name = request.data.get('name', '')
        email = request.data.get('email', '')
        message = request.data.get('message', '')
        if not name or not email or not message:
            return Response({"error": "Barcha maydonlar toldirilishi kerak"}, status=400)
        ContactMessage.objects.create(name=name, email=email, message=message)
        return Response({'message': 'Xabar yuborildi!'})


class AdminStatsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        return Response({
            'users': {
                'total': User.objects.count(),
                'this_week': User.objects.filter(date_joined__gte=week_ago).count(),
                'this_month': User.objects.filter(date_joined__gte=month_ago).count(),
            },
            'questions': {
                'total': Question.objects.count(),
                'this_week': Question.objects.filter(created_at__gte=week_ago).count(),
                'this_month': Question.objects.filter(created_at__gte=month_ago).count(),
            },
            'answers': {
                'total': Answer.objects.count(),
                'this_week': Answer.objects.filter(created_at__gte=week_ago).count(),
            },
            'likes': {
                'total': Like.objects.count(),
            },
            'sessions': {
                'active': UserSession.objects.filter(is_active=True).count(),
            },
            'messages': {
                'total': ContactMessage.objects.count(),
                'unread': ContactMessage.objects.filter(is_read=False).count(),
            },
        })


class AdminUsersView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        data = [{
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'is_staff': u.is_staff,
            'is_active': u.is_active,
            'date_joined': u.date_joined,
            'questions_count': u.questions.count(),
            'answers_count': u.answers.count(),
        } for u in users]
        return Response(data)

    def patch(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            if 'is_active' in request.data:
                user.is_active = request.data['is_active']
            if 'is_staff' in request.data:
                user.is_staff = request.data['is_staff']
            user.save()
            return Response({'message': 'Yangilandi'})
        except User.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)


class AdminQuestionsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        questions = Question.objects.all().order_by('-created_at').select_related('author')
        data = [{
            'id': q.id,
            'title': q.title,
            'author': q.author.username,
            'created_at': q.created_at,
            'answers_count': q.answers.count(),
            'likes_count': q.like_set.count(),
        } for q in questions]
        return Response(data)

    def delete(self, request, question_id):
        try:
            Question.objects.get(id=question_id).delete()
            return Response({"message": "Ochirildi"})
        except Question.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)


class AdminMessagesView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        messages = ContactMessage.objects.all()
        data = [{
            'id': m.id,
            'name': m.name,
            'email': m.email,
            'message': m.message,
            'is_read': m.is_read,
            'created_at': m.created_at,
        } for m in messages]
        return Response(data)

    def patch(self, request, message_id):
        try:
            msg = ContactMessage.objects.get(id=message_id)
            msg.is_read = True
            msg.save()
            return Response({"message": "Oqildi"})
        except ContactMessage.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)


class SavedQuestionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        question_id = request.data.get('question_id')
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Topilmadi'}, status=404)
        saved, created = SavedQuestion.objects.get_or_create(user=request.user, question=question)
        if not created:
            saved.delete()
            return Response({'saved': False})
        return Response({'saved': True})

    def get(self, request):
        saved = SavedQuestion.objects.filter(user=request.user).select_related('question')
        if request.query_params.get('ids_only'):
            return Response({'ids': [s.question_id for s in saved]})
        data = [QuestionSerializer(s.question, context={'request': request}).data for s in saved]
        return Response(data)
