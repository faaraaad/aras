"""
Authentication views: registration, profile, and token logout (blacklist).
"""
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .auth_serializers import (
    UserRegistrationSerializer,
    UserProfileSerializer,
)


class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Create a new user account.
    No authentication required.

    Request body:
        {
            "username": "johndoe",
            "email": "john@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!"
        }

    Returns 201 Created with the new user's id, username, and email.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Issue tokens immediately after registration so the user
        # is logged in right away without a separate /token call.
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                },
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'message': 'Account created successfully.',
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(generics.RetrieveAPIView):
    """
    GET /api/auth/me/
    Returns the currently authenticated user's profile.
    Requires a valid JWT Bearer token.
    """
    serializer_class = UserProfileSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Blacklists the provided refresh token, effectively logging the user out.
    The access token will continue to work until it expires (max 60 min).

    Request body:
        { "refresh": "<refresh_token>" }
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response(
                    {'detail': 'Refresh token is required.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {'detail': 'Successfully logged out.'},
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
