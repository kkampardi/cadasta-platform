from datetime import datetime
from django.test import TestCase
from .factories import UserFactory
from core.tests.utils.cases import UserTestCase
from unittest import mock
from django.conf import settings


class UserTest(TestCase):
    def test_repr(self):
        date = datetime.now()
        user = UserFactory.build(username='John',
                                 full_name='John Lennon',
                                 email='john@beatles.uk',
                                 email_verified=True,
                                 phone='+12025550111',
                                 phone_verified=True)
        assert repr(user) == ('<User username=John'
                              ' full_name=John Lennon'
                              ' email=john@beatles.uk'
                              ' email_verified=True'
                              ' phone=+12025550111'
                              ' phone_verified=True>').format(date)


class VerificationDeviceTest(UserTestCase, TestCase):
    def setUp(self):
        super().setUp()

        self.sherlock = UserFactory.create()
        self.sherlock.verificationdevice_set.create(
            unverified_phone=self.sherlock.phone)

        self.john = UserFactory.create()
        self.john.verificationdevice_set.create(
            unverified_phone=self.john.phone)

        self.TOTP_TOKEN_VALIDITY = settings.TOTP_TOKEN_VALIDITY
        self._now = 1497657600

    def test_instant(self):
        """Verify token as soon as it is created"""
        device = self.sherlock.verificationdevice_set.get()
        with mock_current_time(self._now):
            token = device.generate_challenge()
            verified = device.verify_token(token)

        assert verified is True

    def test_barely_made_it(self):
        """Verify token 1 second before it expires"""
        device = self.sherlock.verificationdevice_set.get()

        with mock_current_time(self._now):
            token = device.generate_challenge()
        with mock_current_time(self._now + self.TOTP_TOKEN_VALIDITY - 1):
            verified = device.verify_token(token)

        assert verified is True

    def test_too_late(self):
        """Verify token 1 second after it expires"""
        device = self.sherlock.verificationdevice_set.get()

        with mock_current_time(self._now):
            token = device.generate_challenge()
        with mock_current_time(self._now + self.TOTP_TOKEN_VALIDITY + 1):
            verified = device.verify_token(token)

        assert verified is False

    def test_future(self):
        """Verify token from the future. Time Travel!!"""
        device = self.sherlock.verificationdevice_set.get()

        with mock_current_time(self._now + 1):
            token = device.generate_challenge()
        with mock_current_time(self._now - 1):
            verified = device.verify_token(token)

        assert verified is False

    def test_code_reuse(self):
        """Verify same token twice"""
        device = self.sherlock.verificationdevice_set.get()

        with mock_current_time(self._now):
            token = device.generate_challenge()
            verified_once = device.verify_token(token)
            verified_twice = device.verify_token(token)

        assert verified_once is True
        assert verified_twice is False

    def test_cross_user(self):
        """Verify token generated by one device with that of another"""
        device_sherlock = self.sherlock.verificationdevice_set.get()
        device_john = self.john.verificationdevice_set.get()

        with mock_current_time(self._now):
            token = device_sherlock.generate_challenge()
            verified = device_john.verify_token(token)

        assert verified is False

    def test_token_invalid(self):
        """Verify an invalid token"""
        device = self.sherlock.verificationdevice_set.get()

        with mock_current_time(self._now):
            token = device.generate_challenge()
            verified_invalid_token = device.verify_token('ABCDEF')
            verified_valid_token = device.verify_token(token)

        assert verified_invalid_token is False
        assert verified_valid_token is True

    def test_two_unverified_phone(self):
        """Verify token generated by device 1 with device 2 of user"""
        self.sherlock.verificationdevice_set.create(
            unverified_phone='+919067439937')

        device_1 = self.sherlock.verificationdevice_set.get(
            unverified_phone=self.sherlock.phone)
        device_2 = self.sherlock.verificationdevice_set.get(
            unverified_phone='+919067439937')

        with mock_current_time(self._now):
            token_device_1 = device_1.generate_challenge()
            verified_device_2 = device_2.verify_token(token_device_1)

        assert verified_device_2 is False


def mock_current_time(timestamp):
    return mock.patch('time.time', lambda: timestamp)
