from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class AuthEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='johndoe',
            email='johndoe@example.com',
            password='Password123!'
        )

    def test_token_obtain_pair_success(self):
        response = self.client.post('/api/auth/token/', {
            'username': 'johndoe',
            'password': 'Password123!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], 'johndoe')

    def test_token_obtain_pair_invalid_credentials(self):
        response = self.client.post('/api/auth/token/', {
            'username': 'johndoe',
            'password': 'WrongPassword',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_register_user_success(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], 'newuser')

    def test_register_password_mismatch(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'mismatchuser',
            'email': 'mismatch@example.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'DifferentPassword123!',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_me_authenticated(self):
        token_res = self.client.post('/api/auth/token/', {
            'username': 'johndoe',
            'password': 'Password123!',
        })
        access_token = token_res.json()['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        profile_res = self.client.get('/api/auth/me/')
        self.assertEqual(profile_res.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_res.json()['username'], 'johndoe')

    def test_profile_me_unauthenticated(self):
        profile_res = self.client.get('/api/auth/me/')
        self.assertEqual(profile_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_verify_endpoint(self):
        token_res = self.client.post('/api/auth/token/', {
            'username': 'johndoe',
            'password': 'Password123!',
        })
        access_token = token_res.json()['access']

        verify_res = self.client.post('/api/auth/token/verify/', {
            'token': access_token,
        })
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)

    def test_token_refresh_endpoint(self):
        token_res = self.client.post('/api/auth/token/', {
            'username': 'johndoe',
            'password': 'Password123!',
        })
        refresh_token = token_res.json()['refresh']

        refresh_res = self.client.post('/api/auth/token/refresh/', {
            'refresh': refresh_token,
        })
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_res.json())

    def test_logout_and_blacklist(self):
        token_res = self.client.post('/api/auth/token/', {
            'username': 'johndoe',
            'password': 'Password123!',
        })
        access_token = token_res.json()['access']
        refresh_token = token_res.json()['refresh']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_res = self.client.post('/api/auth/logout/', {
            'refresh': refresh_token,
        })
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Trying to refresh with blacklisted token should fail
        refresh_res = self.client.post('/api/auth/token/refresh/', {
            'refresh': refresh_token,
        })
        self.assertEqual(refresh_res.status_code, status.HTTP_401_UNAUTHORIZED)
