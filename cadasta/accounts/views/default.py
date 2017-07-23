from django.core.urlresolvers import reverse_lazy
from django.utils.translation import ugettext as _
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import FormView
from django.shortcuts import redirect

from core.views.generic import UpdateView, CreateView
from core.views.mixins import SuperUserCheckMixin

import allauth.account.views as allauth_views
from allauth.account.views import ConfirmEmailView, LoginView
from allauth.account.utils import send_email_confirmation
from allauth.account.models import EmailAddress

from ..models import User, VerificationDevice
from .. import forms


class AccountRegister(CreateView):
    model = User
    form_class = forms.RegisterForm
    template_name = 'account/signup.html'
    success_url = reverse_lazy('account:verify_phone')

    def form_valid(self, form):
        user = form.save(self.request)

        if user.email:
            send_email_confirmation(self.request, user)

        if user.phone:
            device = VerificationDevice.objects.create(
                user=user, unverified_phone=user.phone)
            device.generate_challenge()
            message = _("Verification Token sent to {phone}")
            message = message.format(phone=user.phone)
            messages.add_message(self.request, messages.INFO, message)

        self.request.session['user_id'] = user.id

        message = _("We have created your account. You should have"
                    " received an email or a text to verify your account.")
        messages.add_message(self.request, messages.SUCCESS, message)

        return super().form_valid(form)

    def form_invalid(self, form):
        return super().form_invalid(form)


class PasswordChangeView(LoginRequiredMixin,
                         SuperUserCheckMixin,
                         allauth_views.PasswordChangeView):
    success_url = reverse_lazy('account:profile')
    form_class = forms.ChangePasswordForm


class PasswordResetView(SuperUserCheckMixin,
                        allauth_views.PasswordResetView):
    form_class = forms.ResetPasswordForm


class PasswordResetDoneView(FormView, allauth_views.PasswordResetDoneView):
    form_class = forms.ResetPasswordDoneTokenForm
    success_url = reverse_lazy('account:account_reset_password_from_phone')

    def get_context_data(self, *args, **kwargs):
        context_data = super().get_context_data(*args, **kwargs)
        phone = self.request.session.get('phone', None)
        if phone:
            context_data['phone'] = phone
        return context_data

    def form_valid(self, form):
        token = form.cleaned_data.get('token')
        phone = self.request.session["phone"]
        user = User.objects.get(phone=phone)
        device = user.verificationdevice_set.get(
            unverified_phone=phone,
            label='password_reset')
        if device.verify_token(token):
            message = _("Successfully Verified Token."
                        " You can now reset your password.")
            messages.add_message(self.request, messages.SUCCESS, message)
            VerificationDevice.objects.get(
                user=user,
                unverified_phone=phone,
                label='password_reset').delete()
            return super().form_valid(form)
        elif device.verify_token(token, tolerance=5):
            message = _(
                "Expired token. Please try resetting your password again.")
            messages.add_message(self.request, messages.ERROR, message)
            return redirect(reverse_lazy('account:account_reset_password'))
        else:
            message = _("Invalid Token. Enter a valid token.")
            messages.add_message(self.request, messages.ERROR, message)
            return super().form_invalid(form)


class PasswordResetFromKeyView(SuperUserCheckMixin,
                               allauth_views.PasswordResetFromKeyView):
    form_class = forms.ResetPasswordKeyForm


class PasswordResetFromPhoneView(FormView, SuperUserCheckMixin):
    form_class = forms.ResetPasswordKeyForm
    template_name = 'account/password_reset_from_key.html'
    success_url = reverse_lazy("account:account_reset_password_from_key_done")

    def get_form_kwargs(self, *args, **kwargs):
        form_kwargs = super().get_form_kwargs(*args, **kwargs)
        phone = self.request.session['phone']
        user = User.objects.get(phone=phone)
        form_kwargs["user"] = user
        return form_kwargs

    def form_valid(self, form):
        form.save()
        # send message to user's phone informing that password
        # was successfully changed.
        return super().form_valid(form)


class AccountProfile(LoginRequiredMixin, UpdateView):
    model = User
    form_class = forms.ProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('account:profile')

    def get_object(self, *args, **kwargs):
        self.instance_phone = self.request.user.phone
        return self.request.user

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        emails_to_verify = EmailAddress.objects.filter(
            user=self.object, verified=False).exists()
        phones_to_verify = VerificationDevice.objects.filter(
            user=self.object, verified=False).exists()

        context['emails_to_verify'] = emails_to_verify
        context['phones_to_verify'] = phones_to_verify
        return context

    def get_form_kwargs(self, *args, **kwargs):
        form_kwargs = super().get_form_kwargs(*args, **kwargs)
        form_kwargs['request'] = self.request
        return form_kwargs

    def form_valid(self, form):
        phone = form.data.get('phone')
        messages.add_message(self.request, messages.SUCCESS,
                             _("Successfully updated profile information"))

        if (phone != self.instance_phone and phone):
            message = _("Verification Token sent to {phone}")
            message = message.format(phone=phone)
            messages.add_message(self.request, messages.INFO, message)
            self.request.session["user_id"] = self.object.id
            self.success_url = reverse_lazy('account:verify_phone')

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.add_message(self.request, messages.ERROR,
                             _("Failed to update profile information"))
        return super().form_invalid(form)


class AccountLogin(LoginView):
    def form_valid(self, form):
        user = form.user
        if not user.email_verified:
            user.is_active = False
            user.save()
            send_email_confirmation(self.request, user)

        return super().form_valid(form)


class ConfirmEmail(ConfirmEmailView):

    def post(self, *args, **kwargs):
        response = super().post(*args, **kwargs)

        user = self.get_object().email_address.user
        user.email = self.get_object().email_address.email
        user.email_verified = True
        user.is_active = True
        user.save()

        return response


class ConfirmPhone(FormView):
    template_name = 'accounts/account_verification.html'
    form_class = forms.PhoneVerificationForm
    success_url = reverse_lazy('account:login')

    def get_user(self):
        user_id = self.request.session['user_id']
        user = User.objects.get(id=user_id)
        return user

    def get_form_kwargs(self, *args, **kwargs):
        form_kwargs = super().get_form_kwargs(*args, **kwargs)
        form_kwargs["user"] = self.get_user()
        return form_kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_user()
        if user.emailaddress_set.filter(verified=False).exists():
            context['email'] = user.email
        if VerificationDevice.objects.filter(
                user=user, verified=False).exists():
            context['phone'] = user.phone
        return context

    def form_valid(self, form):
        user = self.get_user()
        user.refresh_from_db()
        message = _("Successfully verified {phone}")
        message = message.format(phone=user.phone)
        messages.add_message(self.request, messages.SUCCESS, message)
        VerificationDevice.objects.get(user=user,
                                       unverified_phone=user.phone,
                                       label='phone_verify').delete()
        return super().form_valid(form)
