from django.utils.translation import ugettext as _
from allauth.account.utils import send_email_confirmation

from rest_framework.serializers import ValidationError
from rest_framework.response import Response
from rest_framework import status

from djoser import views as djoser_views
from djoser import signals
from allauth.account.signals import password_changed

from .. import serializers
from .. import utils
from .. import messages
from ..exceptions import EmailNotVerifiedError
from ..models import VerificationDevice


class AccountUser(djoser_views.UserView):
    serializer_class = serializers.UserSerializer

    def perform_update(self, serializer):
        instance = self.get_object()
        current_email, current_phone = instance.email, instance.phone
        new_email = serializer.validated_data.get('email', instance.email)
        new_phone = serializer.validated_data.get('phone', instance.phone)
        user = serializer.save()

        if current_email != new_email:
            email_set = instance.emailaddress_set.all()
            if email_set.exists():
                email_set.delete()
            if new_email:
                send_email_confirmation(self.request._request, user)
                if current_email:
                    user.email = current_email
                    utils.send_email_update_notification(current_email)
                    email_update_message = messages.email_delete
            else:
                user.email_verified = False
                utils.send_email_deleted_notification(current_email)
                email_update_message = messages.email_delete

        if current_phone != new_phone:
            phone_set = VerificationDevice.objects.filter(user=instance)
            if phone_set.exists():
                phone_set.delete()
            if new_phone:
                device = VerificationDevice.objects.create(
                    user=instance,
                    unverified_phone=new_phone)
                device.generate_challenge()
                if current_phone:
                    user.phone = current_phone
                    utils.send_sms(self.current_phone, messages.phone_change)
                if user.email_verified:
                    utils.send_phone_update_notification(user.email)
            else:
                user.phone_verified = False
                utils.send_sms(self.current_phone, messages.phone_delete)
                if user.email_verified:
                    utils.send_phone_deleted_notification(user.email)

        if user.phone_verified and email_update_message:
            utils.send_sms(to=user.phone, body=email_update_message)
        user.save()


class AccountRegister(djoser_views.RegistrationView):
    serializer_class = serializers.RegistrationSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        signals.user_registered.send(sender=self.__class__, user=user,
                                     request=self.request)

        if user.email:
            send_email_confirmation(self.request._request, user)
        if user.phone:
            verification_device = VerificationDevice.objects.create(
                user=user,
                unverified_phone=user.phone)
            verification_device.generate_challenge()


class AccountLogin(djoser_views.LoginView):
    serializer_class = serializers.AccountLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            return self._action(serializer)
        except ValidationError:
            return Response(
                data=serializer.errors,
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except EmailNotVerifiedError:
            user = serializer.user
            user.is_active = False
            user.save()

            send_email_confirmation(self.request._request, user)

            return Response(
                data={'detail': _("The email has not been verified.")},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class SetPasswordView(djoser_views.SetPasswordView):

    def _action(self, serializer):
        response = super()._action(serializer)
        password_changed.send(sender=self.request.user.__class__,
                              request=self.request._request,
                              user=self.request.user)
        return response
